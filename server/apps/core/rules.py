"""Pure rules for the core app. No ORM access here."""

from datetime import datetime, timedelta

CLOCK_ROLLBACK_TOLERANCE = timedelta(minutes=5)


def is_clock_rollback(now: datetime, last_seen_at: datetime | None) -> bool:
    """True when the device clock moved back more than the tolerance (spec §6.7)."""
    if last_seen_at is None:
        return False
    return now < last_seen_at - CLOCK_ROLLBACK_TOLERANCE


# Backups need room: below this the «مساحة القرص» system bar shows (artboard 6.14 B: «أقل من 2 GB»).
DISK_LOW_BYTES = 2 * 1024**3


def disk_low(free_bytes: int | None) -> bool:
    return free_bytes is not None and free_bytes < DISK_LOW_BYTES
