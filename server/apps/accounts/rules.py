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


# --- Recovery (owner decision 2026-09-29, review C-1) -----------------------------------------------------

MIN_PASSWORD_LENGTH = 8
RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"  # no 0/O, 1/I/L: read from paper without mistakes
RECOVERY_LENGTH = 12
RECOVERY_BASE_LOCK = timedelta(minutes=15)
RECOVERY_MAX_LOCK = timedelta(hours=24)


def password_long_enough(password: str) -> bool:
    return len(password or "") >= MIN_PASSWORD_LENGTH


def format_recovery_code(raw: str) -> str:
    """«ABCD2345EFGH» → «ABCD-2345-EFGH» (easier to write down and read back)."""
    return "-".join(raw[i : i + 4] for i in range(0, len(raw), 4))


def normalize_recovery_code(text: str) -> str:
    """What the owner typed → the stored form: capitals, no spaces or dashes; O/I/L read as the digits they look like
    are not in the alphabet, so they are mapped to the letters that are."""
    cleaned = "".join(ch for ch in (text or "").upper() if ch.isalnum())
    return cleaned.replace("0", "Q").replace("O", "Q").replace("1", "J").replace("I", "J").replace("L", "J")


def recovery_failure(failed: int, locks: int, now: datetime) -> tuple[int, int, datetime | None]:
    """(failed, locks, locked_until) after one more wrong recovery attempt: 5 wrong attempts lock recovery for
    15 minutes, then 1 hour, 4 hours… up to a day — guessing never gets faster (C-1)."""
    failed += 1
    if failed < MAX_FAILED_ATTEMPTS:
        return failed, locks, None
    lock = min(RECOVERY_BASE_LOCK * (4**locks), RECOVERY_MAX_LOCK)
    return 0, locks + 1, now + lock
