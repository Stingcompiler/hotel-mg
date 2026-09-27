"""Key slots (1.1): the hotel key wrapped with an owner's or a manager's password.

A backup made on the reception PC carries one slot per active owner or manager, so the owner opens it on another
PC with his own username and password — no key to copy between PCs. A slot is written whenever that person's
password is known in clear: creating the account, changing its password, or signing in with it (once, for
accounts that existed before 1.1). The install's default password never gets a slot: it is printed in the guide,
and anyone holding a backup file could otherwise open it.

Wrapping uses age's passphrase mode (scrypt, about two seconds per slot), so a slot is only rewritten when needed.
"""

import base64

import pyrage
from django.conf import settings
from pyrage import passphrase

from apps.accounts import rules as account_rules

from . import keys
from .models import BackupKeySlot


def wrap(identity: str, password: str) -> str:
    return base64.b64encode(passphrase.encrypt(identity.encode("ascii"), password)).decode("ascii")


def unwrap(wrapped: str, password: str) -> str | None:
    """The identity, or None for a wrong password or a damaged slot."""
    try:
        return passphrase.decrypt(base64.b64decode(wrapped), password).decode("ascii")
    except (pyrage.DecryptError, ValueError):
        return None


def _eligible(user) -> bool:
    return user.is_active and account_rules.is_manager(user.role) and not user.default_password


def _hotel_pc() -> bool:
    """Slots are written where backups are made: the reception PC (the owner PC only reads them from files)."""
    return settings.SKYTOWERS_ROLE == "reception"


def refresh(user, password: str) -> None:
    """After the password was set or changed: rewrite this person's slot (or drop it when not eligible)."""
    identity = keys.hotel_identity()
    if identity is None or not _hotel_pc():  # an owner PC, or a reception PC before its first start with 1.1
        return
    if not _eligible(user):
        BackupKeySlot.objects.filter(user=user).update(wrapped="")  # rows are never deleted (CLAUDE.md)
        return
    public = str(identity.to_public())
    BackupKeySlot.objects.update_or_create(
        user=user, defaults={"wrapped": wrap(str(identity), password), "recipient": public}
    )


def ensure(user, password: str) -> None:
    """On a password sign-in: write the slot once if this person has none for the current hotel key."""
    identity = keys.hotel_identity()
    if identity is None or not _hotel_pc() or not _eligible(user):
        return
    current = BackupKeySlot.objects.filter(user=user, recipient=str(identity.to_public())).exclude(wrapped="")
    if not current.exists():
        refresh(user, password)


def for_export() -> list[dict]:
    """The slots a new backup carries: active owners and managers, for the current hotel key."""
    identity = keys.hotel_identity()
    if identity is None:
        return []
    rows = (
        BackupKeySlot.objects.filter(
            recipient=str(identity.to_public()), user__is_active=True, user__role__in=account_rules.MANAGER_ROLES
        )
        .exclude(wrapped="")
        .select_related("user")
    )
    return [
        {"username": slot.user.username, "wrapped": slot.wrapped} for slot in rows if not slot.user.default_password
    ]


def clear_if_ineligible(user) -> None:
    """A role or status change without a password: a person who may no longer open backups loses the slot."""
    if not _eligible(user):
        BackupKeySlot.objects.filter(user=user).update(wrapped="")
