"""Clock-rollback guard (spec §6.7).

``observe_clock()`` runs on every write request (middleware) and, from phase B3,
on every scheduler tick. Once blocked, writes stay refused until a manager
approves with a password confirmation (``POST system/clock/approve``).
Both the detection and the approval are audited.
"""

import logging
from datetime import datetime

from django.conf import settings
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
            _audit(None, "system.clock_rollback", {"device_time": now, "last_seen_at": clock.last_seen_at})
            return True
        if clock.last_seen_at is None or now > clock.last_seen_at:
            clock.last_seen_at = now
            clock.save(update_fields=["last_seen_at"])
        return False


def approve_clock(actor=None, now: datetime | None = None) -> None:
    """Manager accepted the current device time: unblock and restart tracking from it."""
    now = now or timezone.now()
    with transaction.atomic():
        clock = SystemClock.load()
        _audit(actor, "system.clock_approve", {"device_time": now, "blocked_at": clock.blocked_at})
        clock.clock_blocked = False
        clock.blocked_at = None
        clock.last_seen_at = now
        clock.save()


def _audit(actor, action: str, after: dict) -> None:
    if settings.RUNTIME.hotel_id is None:
        return  # owner PC before its first import has no chain to write to
    from apps.audit import services as audit  # core must not import audit at module load

    audit.record(actor=actor, action=action, entity="system_clock", entity_id="1", after=after)
