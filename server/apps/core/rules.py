"""Pure rules for the core app. No ORM access here."""

from datetime import datetime, timedelta

CLOCK_ROLLBACK_TOLERANCE = timedelta(minutes=5)


def is_clock_rollback(now: datetime, last_seen_at: datetime | None) -> bool:
    """True when the device clock moved back more than the tolerance (spec §6.7)."""
    if last_seen_at is None:
        return False
    return now < last_seen_at - CLOCK_ROLLBACK_TOLERANCE
