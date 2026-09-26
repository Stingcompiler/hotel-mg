"""Clock-rollback guard (spec §6.7).

``observe_clock()`` runs on every write request (middleware) and, from phase B3,
on every scheduler tick. Once blocked, writes stay refused until a manager
approves; the approve endpoint (password confirmation) and the audit entries
arrive with auth (B1) and the scheduler (B3).
"""

import logging
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from . import rules
from .models import SystemClock

log = logging.getLogger(__name__)


def is_clock_blocked() -> bool:
    return SystemClock.objects.filter(pk=1, clock_blocked=True).exists()


def observe_clock(now: datetime | None = None) -> bool:
    """Record the current time; return True when writes must be refused."""
    now = now or timezone.now()
    with transaction.atomic():
        clock = SystemClock.load()
        if clock.clock_blocked:
            return True
        if rules.is_clock_rollback(now, clock.last_seen_at):
            clock.clock_blocked = True
            clock.blocked_at = now
            clock.save(update_fields=["clock_blocked", "blocked_at"])
            log.warning("Clock rollback detected: now=%s last_seen_at=%s", now, clock.last_seen_at)
            return True
        if clock.last_seen_at is None or now > clock.last_seen_at:
            clock.last_seen_at = now
            clock.save(update_fields=["last_seen_at"])
        return False


def approve_clock(now: datetime | None = None) -> None:
    """Manager accepted the current device time: unblock and restart tracking from it."""
    now = now or timezone.now()
    with transaction.atomic():
        clock = SystemClock.load()
        clock.clock_blocked = False
        clock.blocked_at = None
        clock.last_seen_at = now
        clock.save()
