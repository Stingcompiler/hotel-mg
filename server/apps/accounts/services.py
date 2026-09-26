"""Account use cases. Each runs in one transaction and writes its audit row (spec §4, §6.8).

Failed logins must persist even though the request fails, so login services
return a result and the view raises the API error after the transaction commits.
"""

from dataclasses import dataclass
from datetime import datetime

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
USER_FIELDS = ["username", "full_name", "role", "is_active", "is_staff", "failed_attempts", "locked_until"]


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


@transaction.atomic
def login_with_pin(user_id, pin: str) -> LoginResult:
    user = User.objects.filter(pk=user_id).first()
    return _check_credential(user, lambda u: u.check_pin(pin), LoginEvent.Kind.PIN)


@transaction.atomic
def login_with_password(username: str, password: str) -> LoginResult:
    user = User.objects.filter(username=username).first()
    return _check_credential(user, lambda u: u.check_password(password), LoginEvent.Kind.PASSWORD)


@transaction.atomic
def check_password_for_confirmation(user: User, password: str) -> LoginResult:
    return _check_credential(user, lambda u: u.check_password(password), kind=None)


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


def issue_confirm_token(user: User, password: str) -> str:
    """Re-check the password and return a 5-minute confirmation token (sent as X-Confirm-Token)."""
    raise_for_login(check_password_for_confirmation(user, password))
    return signing.dumps({"u": str(user.pk)}, salt=CONFIRM_SALT)


def require_confirmation(request) -> None:
    """Raise 403 ``confirmation_required`` unless the request carries a fresh token for this user."""
    raw = request.headers.get("X-Confirm-Token", "")
    try:
        data = signing.loads(raw, salt=CONFIRM_SALT, max_age=rules.CONFIRM_LIFETIME)
    except signing.BadSignature:
        raise ApiError("confirmation_required", 403) from None
    if data.get("u") != str(request.user.pk):
        raise ApiError("confirmation_required", 403)


# --- User management (manager+) ------------------------------------------------


def _ensure_can_manage(actor: User, target_role: str) -> None:
    if not rules.can_manage_user(actor.role, target_role):
        raise ApiError("permission_denied", 403)


@transaction.atomic
def create_user(actor: User, *, username, full_name, role, pin, password=None) -> User:
    _ensure_can_manage(actor, role)
    user = User.objects.create_user(
        username,
        full_name,
        role=role,
        pin=pin,
        password=password,
        is_staff=rules.is_manager(role),
        created_by=actor,
    )
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
    before = audit.snapshot(user, USER_FIELDS)
    password = changes.pop("password", None)
    for field, value in changes.items():
        setattr(user, field, value)
    if password:
        user.set_password(password)
    if "role" in changes:
        user.is_staff = rules.is_manager(user.role)
    user.full_clean(exclude=["password", "hotel_id"])
    user.save()
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
    user.save(update_fields=["pin_hash", "failed_attempts", "locked_until"])
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
        if not rules.is_locked(manager.locked_until, now) and manager.check_password(password or ""):
            if manager.failed_attempts:
                manager.failed_attempts, manager.locked_until = 0, None
                _save_counters(manager, "failed_attempts", "locked_until")
            return manager
    raise ApiError("override_invalid", 403)


@transaction.atomic
def register_override_failure() -> None:
    """A wrong override password counts as a failed attempt for every manager who could have typed it
    (the screen has one shared field), so the 5-attempt lock of spec §5 throttles guessing here too."""
    now = timezone.now()
    for manager in User.objects.filter(role__in=rules.MANAGER_ROLES, is_active=True):
        if rules.is_locked(manager.locked_until, now):
            continue
        before = audit.snapshot(manager, USER_FIELDS)
        manager.failed_attempts, manager.locked_until = rules.register_failure(manager.failed_attempts, now)
        _save_counters(manager, "failed_attempts", "locked_until")
        LoginEvent.objects.create(user=manager, at=now, kind=LoginEvent.Kind.FAILED, created_by=manager)
        if manager.locked_until:
            audit.record(
                actor=manager,
                action="auth.locked",
                entity="user",
                entity_id=manager.pk,
                before=before,
                after=audit.snapshot(manager, USER_FIELDS),
            )
