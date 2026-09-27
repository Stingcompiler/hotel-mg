"""Pure rules for accounts. No ORM access here."""

import re
from datetime import datetime, timedelta

_PIN = re.compile(r"[0-9]{4,6}")

MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION = timedelta(minutes=5)
SESSION_LIFETIME = timedelta(hours=12)
CONFIRM_LIFETIME = timedelta(minutes=5)

MANAGER_ROLES = frozenset({"manager", "owner"})

# The account a new install starts with (owner decision 2026-09-27): no setup screen, the login page shows these
# until the password is changed, and a reminder after login suggests changing them (not forced).
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "123456"
DEFAULT_PIN = "123456"
DEFAULT_FULL_NAME = "المالك"


def is_valid_pin(pin: str) -> bool:
    """PIN is 4-6 ASCII digits (spec §5)."""
    return isinstance(pin, str) and _PIN.fullmatch(pin) is not None


def is_locked(locked_until: datetime | None, now: datetime) -> bool:
    return locked_until is not None and now < locked_until


def register_failure(failed_attempts: int, now: datetime) -> tuple[int, datetime | None]:
    """Return (failed_attempts, locked_until) after one more failed login.

    The 5th failure locks for 5 minutes and resets the counter (spec §5).
    """
    attempts = failed_attempts + 1
    if attempts >= MAX_FAILED_ATTEMPTS:
        return 0, now + LOCK_DURATION
    return attempts, None


def attempts_left(failed_attempts: int) -> int:
    return MAX_FAILED_ATTEMPTS - failed_attempts


def is_manager(role: str) -> bool:
    return role in MANAGER_ROLES


def can_manage_user(actor_role: str, target_role: str) -> bool:
    """Managers manage reception and manager accounts; only the owner manages owner accounts."""
    if actor_role == "owner":
        return True
    return actor_role == "manager" and target_role != "owner"


def token_expired(created: datetime, now: datetime) -> bool:
    return now >= created + SESSION_LIFETIME
