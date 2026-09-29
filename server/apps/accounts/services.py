"""Account use cases. Each runs in one transaction and writes its audit row (spec §4, §6.8).

Failed logins must persist even though the request fails, so login services
return a result and the view raises the API error after the transaction commits.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime

from django.contrib.auth.hashers import check_password, make_password
from django.core import signing
from django.db import transaction
from django.utils import timezone
from rest_framework.authtoken.models import Token

from apps.audit import services as audit
from apps.core.concurrency import get_for_update
from apps.core.errors import ApiError

from . import rules
from .models import LoginEvent, Role, User

CONFIRM_SALT = "skytowers.confirm"
USER_FIELDS = ["username", "full_name", "email", "role", "is_active", "is_staff", "failed_attempts", "locked_until"]


@dataclass(frozen=True)
class LoginResult:
    ok: bool = False
    user: User | None = None
    token: str | None = None
    attempts_left: int | None = None
    locked_until: datetime | None = None


def _save_counters(user: User, *fields: str) -> None:
    """Login bookkeeping without touching ``version``/``updated_at``: a login is not an edit of the user,
    and on the owner PC a newer ``updated_at`` would hide the reception's real edits at the next import."""
    User.objects.filter(pk=user.pk).update(**{f: getattr(user, f) for f in fields})


def _check_credential(user: User | None, credential_ok, kind: str | None) -> LoginResult:
    """Shared flow for PIN login, password login and password confirmation.

    Handles lockout and the failure counter; ``kind=None`` (confirmation) opens no session.
    """
    now = timezone.now()
    if user is None or not user.is_active:
        return LoginResult()
    if rules.is_locked(user.locked_until, now):
        return LoginResult(user=user, locked_until=user.locked_until)

    before = audit.snapshot(user, USER_FIELDS)
    if not credential_ok(user):
        user.failed_attempts, user.locked_until = rules.register_failure(user.failed_attempts, now)
        _save_counters(user, "failed_attempts", "locked_until")
        LoginEvent.objects.create(user=user, at=now, kind=LoginEvent.Kind.FAILED, created_by=user)
        if user.locked_until:
            audit.record(
                actor=user,
                action="auth.locked",
                entity="user",
                entity_id=user.pk,
                before=before,
                after=audit.snapshot(user, USER_FIELDS),
            )
            return LoginResult(user=user, locked_until=user.locked_until)
        return LoginResult(user=user, attempts_left=rules.attempts_left(user.failed_attempts))

    if kind is None:
        if user.failed_attempts:
            user.failed_attempts = 0
            _save_counters(user, "failed_attempts")
        return LoginResult(ok=True, user=user)

    user.failed_attempts, user.locked_until, user.last_login = 0, None, now
    _save_counters(user, "failed_attempts", "locked_until", "last_login")
    LoginEvent.objects.create(user=user, at=now, kind=kind, created_by=user)
    Token.objects.filter(user=user).delete()
    token = Token.objects.create(user=user)
    audit.record(actor=user, action=f"auth.login_{kind}", entity="user", entity_id=user.pk)
    return LoginResult(ok=True, user=user, token=token.key)


def _hash_first(user: User | None, check) -> bool:
    """The password or PIN hash is checked before the write transaction. SQLite transactions here are IMMEDIATE:
    hashing inside one held every other write (a payment at the desk) for up to 3 s (review 2026-09-29, F-10).
    A locked account is not checked at all, as before."""
    return (
        user is not None
        and user.is_active
        and not rules.is_locked(user.locked_until, timezone.now())
        and bool(check(user))
    )


def login_with_pin(user_id, pin: str) -> LoginResult:
    ok = _hash_first(User.objects.filter(pk=user_id).first(), lambda u: u.check_pin(pin))
    with transaction.atomic():
        user = User.objects.filter(pk=user_id).first()  # counters as they are now, under the lock
        return _check_credential(user, lambda u: ok, LoginEvent.Kind.PIN)


def login_with_password(username: str, password: str) -> LoginResult:
    ok = _hash_first(User.objects.filter(username=username).first(), lambda u: u.check_password(password))
    with transaction.atomic():
        user = User.objects.filter(username=username).first()
        result = _check_credential(user, lambda u: ok, LoginEvent.Kind.PASSWORD)
        if result.ok:
            # Accounts from before 1.1 get their backup key slot at their first password sign-in.
            _backup_slot(result.user, password, on_login=True)
        return result


def _require_password_length(password: str) -> None:
    if not rules.password_long_enough(password):
        raise ApiError("validation_error", 400, detail=f"كلمة المرور {rules.MIN_PASSWORD_LENGTH} أحرف على الأقل.")


def new_recovery_code(user: User) -> str:
    """A fresh one-time recovery code for the owner (shown once, stored hashed); the old one stops working."""
    raw = "".join(secrets.choice(rules.RECOVERY_ALPHABET) for _ in range(rules.RECOVERY_LENGTH))
    user.recovery_code_hash = make_password(raw)
    user.save(update_fields=["recovery_code_hash"])
    return rules.format_recovery_code(raw)


@transaction.atomic
def issue_recovery_code(actor: User, user_id) -> str:
    """«رمز استعادة جديد»: the owner, for his own account (confirmed with his password by the view)."""
    user = User.objects.select_for_update().get(pk=user_id)
    if user.pk != actor.pk or user.role != "owner":
        raise ApiError("permission_denied", 403)
    code = new_recovery_code(user)
    audit.record(actor=actor, action="user.recovery_code", entity="user", entity_id=user.pk)
    return code


@transaction.atomic
def recover_password(username: str, password: str, email: str = "", recovery_code: str = "") -> tuple[LoginResult, str]:
    """«نسيت كلمة المرور؟» on the reception PC, offline.

    The owner proves it with his one-time recovery code (owner decision 2026-09-29, review C-1) and receives a new
    one; other accounts with a password use the email saved on them. Wrong attempts have their own escalating lock
    and never lock the normal sign-in (C-4). The new password signs every session out, unlocks the account and
    rewrites the backup key slot. Returns (result, new recovery code or "").
    """
    _require_password_length(password)
    now = timezone.now()
    user = User.objects.select_for_update().filter(username=username.strip(), is_active=True).first()
    if user is None:
        return LoginResult(), ""
    if rules.is_locked(user.recovery_locked_until, now):
        return LoginResult(user=user, locked_until=user.recovery_locked_until), ""
    if user.role == "owner":
        code = rules.normalize_recovery_code(recovery_code)
        ok = bool(code) and bool(user.recovery_code_hash) and check_password(code, user.recovery_code_hash)
    else:
        wanted = email.strip().lower()
        ok = user.has_usable_password() and bool(user.email) and user.email.lower() == wanted  # C-3: no PIN-only
    if not ok:
        user.recovery_failed, user.recovery_locks, user.recovery_locked_until = rules.recovery_failure(
            user.recovery_failed, user.recovery_locks, now
        )
        _save_counters(user, "recovery_failed", "recovery_locks", "recovery_locked_until")
        if user.recovery_locked_until:
            audit.record(actor=user, action="auth.recovery_locked", entity="user", entity_id=user.pk)
            return LoginResult(user=user, locked_until=user.recovery_locked_until), ""
        return LoginResult(user=user, attempts_left=rules.attempts_left(user.recovery_failed)), ""
    before = audit.snapshot(user, USER_FIELDS)
    user.set_password(password)
    user.default_password = False
    user.failed_attempts, user.locked_until = 0, None
    user.recovery_failed, user.recovery_locks, user.recovery_locked_until = 0, 0, None
    user.save()
    Token.objects.filter(user=user).delete()
    _backup_slot(user, password)
    code = new_recovery_code(user) if user.role == "owner" else ""
    audit.record(
        actor=user,
        action="user.recover_password",
        entity="user",
        entity_id=user.pk,
        before=before,
        after=audit.snapshot(user, USER_FIELDS),
    )
    return LoginResult(ok=True, user=user), code


@transaction.atomic
def reset_password_offline(username: str, password: str) -> User:
    """``manage reset_password``: an administrator of the reception PC sets a new password (the owner forgot the only
    owner password). Unlocks the account and rewrites its backup key slot, so backups keep opening elsewhere."""
    _require_password_length(password)
    user = User.objects.select_for_update().filter(username=username).first()
    if user is None:
        raise ApiError("not_found", 404, detail=f"لا يوجد مستخدم باسم {username}.")
    before = audit.snapshot(user, USER_FIELDS)
    user.set_password(password)
    user.default_password = False
    user.failed_attempts, user.locked_until = 0, None
    user.is_active = True
    user.save()
    _backup_slot(user, password)
    audit.record(
        actor=None,
        action="user.reset_password_offline",
        entity="user",
        entity_id=user.pk,
        before=before,
        after=audit.snapshot(user, USER_FIELDS),
    )
    return user


def _backup_slot(user: User, password: str | None, on_login: bool = False) -> None:
    """Keep this person's backup key slot in step with the password (apps.backup.keyslots)."""
    from apps.backup import keyslots  # accounts must not import backup at load time

    if password and on_login:
        keyslots.ensure(user, password)
    elif password:
        keyslots.refresh(user, password)
    else:
        keyslots.clear_if_ineligible(user)


def check_password_for_confirmation(user: User, password: str) -> LoginResult:
    ok = _hash_first(User.objects.filter(pk=user.pk).first(), lambda u: u.check_password(password))
    with transaction.atomic():
        return _check_credential(User.objects.filter(pk=user.pk).first(), lambda u: ok, kind=None)


def raise_for_login(result: LoginResult) -> None:
    """Raise the API error for a failed result. Call after the service transaction committed."""
    if result.locked_until:
        raise ApiError("account_locked", 423, locked_until=result.locked_until.isoformat())
    if not result.ok:
        extra = {"attempts_left": result.attempts_left} if result.attempts_left is not None else {}
        raise ApiError("authentication_failed", 401, **extra)


@transaction.atomic
def logout(user: User) -> None:
    Token.objects.filter(user=user).delete()
    audit.record(actor=user, action="auth.logout", entity="user", entity_id=user.pk)


# --- Password confirmation for sensitive actions (spec §6.8) -------------------


def _session_tag(session_key: str) -> str:
    return hashlib.sha256((session_key or "").encode()).hexdigest()[:16]


def issue_confirm_token(user: User, password: str, session_key: str = "") -> str:
    """Re-check the password and return a 5-minute confirmation token (sent as X-Confirm-Token), valid only in the
    session that asked for it: signing out or in again voids it (review 2026-09-29, C-7)."""
    raise_for_login(check_password_for_confirmation(user, password))
    return signing.dumps({"u": str(user.pk), "s": _session_tag(session_key)}, salt=CONFIRM_SALT)


def require_confirmation(request) -> None:
    """Raise 403 ``confirmation_required`` unless the request carries a fresh token for this user."""
    raw = request.headers.get("X-Confirm-Token", "")
    try:
        data = signing.loads(raw, salt=CONFIRM_SALT, max_age=rules.CONFIRM_LIFETIME)
    except signing.BadSignature:
        raise ApiError("confirmation_required", 403) from None
    session_key = getattr(request.auth, "key", "") or ""
    if data.get("u") != str(request.user.pk) or data.get("s") != _session_tag(session_key):
        raise ApiError("confirmation_required", 403)


# --- User management (manager+) ------------------------------------------------


def _ensure_can_manage(actor: User, target_role: str) -> None:
    if not rules.can_manage_user(actor.role, target_role):
        raise ApiError("permission_denied", 403)


@transaction.atomic
def create_user(actor: User, *, username, full_name, role, pin, password=None, email="") -> User:
    _ensure_can_manage(actor, role)
    user = User.objects.create_user(
        username,
        full_name,
        role=role,
        pin=pin,
        password=password,
        email=email.strip().lower(),
        is_staff=rules.is_manager(role),
        created_by=actor,
    )
    _backup_slot(user, password)
    audit.record(
        actor=actor, action="user.create", entity="user", entity_id=user.pk, after=audit.snapshot(user, USER_FIELDS)
    )
    return user


@transaction.atomic
def _create_first_manager(*, username, full_name, password, pin) -> User:
    if User.objects.select_for_update().exists():
        raise ApiError("setup_done", 409)
    user = User.objects.create_user(username, full_name, role=Role.MANAGER, pin=pin, password=password, is_staff=True)
    audit.record(
        actor=None, action="user.create", entity="user", entity_id=user.pk, after=audit.snapshot(user, USER_FIELDS)
    )
    return user


@transaction.atomic
def ensure_default_owner() -> User | None:
    """A new install opens on the login page, not a setup form (owner decision 2026-09-27).

    On a hotel PC with no users yet, create the owner account ``admin`` with the default password and PIN; the
    login page shows them until the password is changed. Returns the account when it was created.
    """
    if User.objects.select_for_update().exists():
        return None
    user = User.objects.create_user(
        rules.DEFAULT_USERNAME,
        rules.DEFAULT_FULL_NAME,
        role=Role.OWNER,
        password=rules.DEFAULT_PASSWORD,
        pin=rules.DEFAULT_PIN,
        is_staff=True,
        default_password=True,
    )
    audit.record(
        actor=None, action="user.create", entity="user", entity_id=user.pk, after=audit.snapshot(user, USER_FIELDS)
    )
    return user


def setup_first_manager(*, username, full_name, password, pin) -> LoginResult:
    """First run on a new reception PC (no users yet): create the manager from the login screen and sign in.

    Replaces `manage createsuperuser` so a non-technical owner can install without a command line.
    """
    _create_first_manager(username=username, full_name=full_name, password=password, pin=pin)
    return login_with_password(username, password)


@transaction.atomic
def update_user(actor: User, user_id, *, version: int, **changes) -> User:
    user = get_for_update(User.objects, user_id, version)
    _ensure_can_manage(actor, user.role)
    if "role" in changes:
        _ensure_can_manage(actor, changes["role"])
    if user.pk == actor.pk and (changes.get("is_active") is False or changes.get("role", actor.role) != actor.role):
        raise ApiError("permission_denied", 403, detail="لا يمكنك تعطيل حسابك أو تغيير دورك.")
    if "username" in changes and User.objects.exclude(pk=user.pk).filter(username=changes["username"]).exists():
        raise ApiError("username_taken", 400)
    before = audit.snapshot(user, USER_FIELDS)
    password = changes.pop("password", None)
    if "email" in changes:
        changes["email"] = changes["email"].strip().lower()
    for field, value in changes.items():
        setattr(user, field, value)
    if password:
        _require_password_length(password)
        user.set_password(password)
        user.default_password = False  # the login page stops showing the install's default
    if "role" in changes:
        user.is_staff = rules.is_manager(user.role)
    user.full_clean(exclude=["password", "hotel_id"])
    user.save()
    _backup_slot(user, password)
    if password and user.role == "owner":
        user.new_recovery_code = new_recovery_code(user)  # shown once in the answer (C-1)
    if changes.get("is_active") is False:
        Token.objects.filter(user=user).delete()
    audit.record(
        actor=actor,
        action="user.update",
        entity="user",
        entity_id=user.pk,
        before=before,
        after=audit.snapshot(user, USER_FIELDS),
    )
    return user


@transaction.atomic
def reset_pin(actor: User, user_id, pin: str) -> User:
    user = User.objects.get(pk=user_id)
    _ensure_can_manage(actor, user.role)
    user.set_pin(pin)
    user.failed_attempts, user.locked_until = 0, None
    user.save(update_fields=["pin_hash", "default_pin", "failed_attempts", "locked_until"])
    audit.record(actor=actor, action="user.reset_pin", entity="user", entity_id=user.pk)
    return user


@transaction.atomic
def unlock_user(actor: User, user_id) -> User:
    user = User.objects.get(pk=user_id)
    _ensure_can_manage(actor, user.role)
    before = audit.snapshot(user, USER_FIELDS)
    user.failed_attempts, user.locked_until = 0, None
    user.save(update_fields=["failed_attempts", "locked_until"])
    audit.record(
        actor=actor,
        action="user.unlock",
        entity="user",
        entity_id=user.pk,
        before=before,
        after=audit.snapshot(user, USER_FIELDS),
    )
    return user


# --- Manager override on another user's session (spec §6.4 checkout with debt) --------------------


def verify_manager_override(password: str, reason: str) -> User:
    """Return the manager/owner whose password was typed on the reception screen, or raise.

    Used where the design asks for «كلمة مرور المدير» plus a reason. The approver is recorded in audit.
    A wrong password raises ``override_invalid``; the API error handler then calls
    :func:`register_override_failure` outside the caller's (rolled-back) transaction.
    """
    if not reason or not reason.strip():
        raise ApiError("reason_required", 400)
    now = timezone.now()
    for manager in User.objects.filter(role__in=rules.MANAGER_ROLES, is_active=True):
        if not rules.is_locked(manager.override_locked_until, now) and manager.check_password(password or ""):
            if manager.override_failed:
                manager.override_failed, manager.override_locked_until = 0, None
                _save_counters(manager, "override_failed", "override_locked_until")
            return manager
    raise ApiError("override_invalid", 403)


@transaction.atomic
def register_override_failure() -> None:
    """A wrong override password counts as a failed attempt for every manager who could have typed it
    (the screen has one shared field), so the 5-attempt lock of spec §5 throttles guessing here too."""
    now = timezone.now()
    for manager in User.objects.filter(role__in=rules.MANAGER_ROLES, is_active=True):
        if rules.is_locked(manager.override_locked_until, now):
            continue
        manager.override_failed, manager.override_locked_until = rules.register_failure(manager.override_failed, now)
        _save_counters(manager, "override_failed", "override_locked_until")
        if manager.override_locked_until:
            # The approval field is locked for a while; the manager's own sign-in is untouched (C-4).
            audit.record(actor=manager, action="auth.override_locked", entity="user", entity_id=manager.pk)
