"""Alert engine (spec §6.6). ``tick()`` runs every 60 s from the scheduler; it is idempotent and catches up.

Each tick, in one transaction:
1. create tasks that fell due (missed ones keep their original ``due_at``);
2. wake snoozed/waiting tasks whose time came;
3. escalate long-open tasks to neglected, recording the open shift;
4. queue Windows toasts for open tasks at their alert/repeat times.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from apps.billing.services import FolioTotals
from apps.cash.models import Shift
from apps.cash.services import current_shift
from apps.core.clock import observe_clock
from apps.rooms.models import Room, RoomStatus
from apps.stays import rules as stay_rules
from apps.stays.models import DurationKind, ReservationStatus, Stay

from . import rules
from .models import AlertRule, FollowupTask, Toast, TriggerKind


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.TIME_ZONE)


def _local_date(dt: datetime):
    return dt.astimezone(_tz()).date()


def _stay_kind(stay: Stay) -> str:
    """Mixed stays follow the daily rule (they end like daily stays)."""
    kind = stay.reservation.duration_kind
    return "daily" if kind == DurationKind.MIXED else kind


def _create(rule: AlertRule, subject_key: str, due_at: datetime, title: str, *, second_at=None, **links) -> bool:
    """Insert once per (rule, subject, due date); a concurrent or repeated tick is a no-op."""
    if FollowupTask.objects.filter(rule=rule, subject_key=subject_key, due_date=_local_date(due_at)).exists():
        return False
    try:
        with transaction.atomic():
            FollowupTask.objects.create(
                rule=rule,
                subject_key=subject_key,
                due_at=due_at,
                due_date=_local_date(due_at),
                second_at=second_at,
                title=title,
                **links,
            )
    except IntegrityError:
        return False
    return True


# --- Generators per trigger ------------------------------------------------------------------


def _in_house():
    return Stay.objects.filter(reservation__status=ReservationStatus.CHECKED_IN).select_related(
        "reservation__guest", "reservation__room"
    )


def _stay_title(stay: Stay, today) -> str:
    r = stay.reservation
    return rules.toast_title(r.room.number, rules.when_text(stay_rules.last_night(r.check_out_date), today))


def stay_ending_due(rule: AlertRule, stay: Stay) -> tuple[datetime, datetime | None]:
    last = stay_rules.last_night(stay.reservation.check_out_date)
    due = rules.first_alert_at(last, rule.days_before, rule.at_time, _tz())
    second = None
    if rule.second_days_before is not None:
        second = rules.first_alert_at(last, rule.second_days_before, rule.at_time, _tz())
    return due, second


def _gen_stay_ending(rule: AlertRule, now: datetime) -> int:
    created, today = 0, _local_date(now)
    for stay in _in_house():
        if _stay_kind(stay) != rule.duration_kind:
            continue
        due, second = stay_ending_due(rule, stay)
        # A stay booked for fewer days than the rule's lead time: alert from the moment it began.
        due = max(due, stay.checked_in_at)
        if rules.is_due(due, now):
            created += _create(
                rule,
                f"stay:{stay.pk}",
                due,
                _stay_title(stay, today),
                second_at=second,
                stay=stay,
                room=stay.reservation.room,
            )
    return created


def _gen_stay_overdue(rule: AlertRule, now: datetime) -> int:
    created, today = 0, _local_date(now)
    for stay in _in_house().filter(reservation__check_out_date__lte=today):
        # «at end»: right after the last night ends.
        due = datetime.combine(stay.reservation.check_out_date, datetime.min.time(), tzinfo=_tz())
        created += _create(
            rule, f"stay:{stay.pk}", due, _stay_title(stay, today), stay=stay, room=stay.reservation.room
        )
    return created


def _gen_checkout_debt(rule: AlertRule, now: datetime) -> int:
    created = 0
    threshold = rule.threshold or 0
    recent = now - timedelta(days=60)
    for stay in Stay.objects.filter(
        reservation__status=ReservationStatus.CHECKED_OUT, checked_out_at__gte=recent, override_by__isnull=False
    ).select_related("reservation__room", "reservation__guest"):
        balance = FolioTotals.of(stay.reservation.folio).balance
        if balance > threshold:
            r = stay.reservation
            title = f"غرفة {r.room.number} — خروج بدين {balance // 100:,}"[:40]
            created += _create(rule, f"stay:{stay.pk}", stay.checked_out_at, title, stay=stay, room=r.room)
    return created


def _gen_shift_too_long(rule: AlertRule, now: datetime) -> int:
    created = 0
    limit = timedelta(hours=rule.threshold_hours or 14)
    for shift in Shift.objects.filter(closed_at__isnull=True, opened_at__lte=now - limit):
        created += _create(
            rule,
            f"shift:{shift.pk}",
            shift.opened_at + limit,
            f"وردية مفتوحة منذ أكثر من {int(limit.total_seconds() // 3600)} ساعة",
            shift=shift,
        )
    return created


def _gen_room_status_too_long(rule: AlertRule, now: datetime, status: str, default_hours: int) -> int:
    created = 0
    limit = timedelta(hours=rule.threshold_hours or default_hours)
    for room in Room.objects.filter(status=status, in_service=True, status_changed_at__lte=now - limit):
        label = "تحتاج تنظيف" if status == RoomStatus.CLEANING else "في الصيانة"
        created += _create(
            rule,
            f"room:{room.pk}:{room.status_changed_at:%Y%m%d%H%M}",
            room.status_changed_at + limit,
            f"غرفة {room.number} — {label} منذ مدة طويلة",
            room=room,
        )
    return created


def _gen_no_backup(rule: AlertRule, now: datetime) -> int:
    from apps.backup.export import last_backup_at  # backup is optional on this device

    limit = timedelta(hours=rule.threshold_hours or 24)
    last = last_backup_at()
    anchor = last or Shift.objects.order_by("opened_at").values_list("opened_at", flat=True).first()
    if anchor is None or now - anchor < limit:
        return 0
    return _create(
        rule, "backup", anchor + limit, f"لا نسخة احتياطية منذ أكثر من {int(limit.total_seconds() // 3600)} ساعة"
    )


GENERATORS = {
    TriggerKind.STAY_ENDING: _gen_stay_ending,
    TriggerKind.STAY_OVERDUE: _gen_stay_overdue,
    TriggerKind.CHECKOUT_DEBT: _gen_checkout_debt,
    TriggerKind.SHIFT_OPEN_TOO_LONG: _gen_shift_too_long,
    TriggerKind.ROOM_CLEANING_TOO_LONG: lambda r, n: _gen_room_status_too_long(r, n, RoomStatus.CLEANING, 4),
    TriggerKind.ROOM_MAINTENANCE_TOO_LONG: lambda r, n: _gen_room_status_too_long(r, n, RoomStatus.MAINTENANCE, 168),
    TriggerKind.NO_BACKUP: _gen_no_backup,
    # no_drive_upload: with Drive sync (phase B4.2).
}


# --- Transitions and notifications ------------------------------------------------------------


def _wake(now: datetime) -> int:
    woke = 0
    for task in FollowupTask.objects.filter(status__in=["snoozed", "waiting"], next_at__lte=now):
        if rules.wakes_up(task.status, task.next_at, now):
            task.status = FollowupTask.Status.OPEN
            task.last_notified_at = None  # notify again now
            task.save(update_fields=["status", "last_notified_at"])
            woke += 1
    return woke


def _escalate(now: datetime) -> int:
    escalated, shift = 0, current_shift()
    for task in FollowupTask.objects.filter(status="open").select_related("rule"):
        if rules.should_escalate(task.status, task.due_at, task.rule.escalate_after_hours, now):
            task.status = FollowupTask.Status.NEGLECTED
            task.neglected_at = now
            if task.shift_id is None:
                task.shift = shift  # «مُهمَلة — وردية: أحمد»: the shift responsible, not whoever is here now
            task.save(update_fields=["status", "neglected_at", "shift"])
            escalated += 1
    return escalated


def _toast_text(task: FollowupTask, now: datetime) -> tuple[str, str]:
    if task.stay_id:
        r = task.stay.reservation
        title = rules.toast_title(
            r.room.number, rules.when_text(stay_rules.last_night(r.check_out_date), _local_date(now))
        )
        return title, rules.toast_body(r.guest.full_name, DurationKind(r.duration_kind).label)
    return task.title[:40], "انقر للفتح"


def _notify(now: datetime) -> int:
    sent = 0
    seq = (Toast.objects.aggregate(m=Max("seq"))["m"] or 0) + 1
    tasks = FollowupTask.objects.filter(status__in=["open", "neglected"]).select_related(
        "rule", "stay__reservation__room", "stay__reservation__guest"
    )
    for task in tasks:
        schedule = rules.notification_times(task.due_at, task.second_at, task.rule.repeat_hours, now)
        latest = schedule[-1] if schedule else None
        if latest is None or (task.last_notified_at and task.last_notified_at >= latest):
            continue
        if task.rule.windows_notification:
            title, body = _toast_text(task, now)
            Toast.objects.create(task=task, seq=seq, title=title, body=body, at=now)
            seq += 1
            sent += 1
        task.last_notified_at = now
        task.save(update_fields=["last_notified_at"])
    return sent


def tick(now: datetime | None = None) -> dict:
    """One engine pass. Skips everything while the clock guard blocks writes (spec §6.7)."""
    now = now or timezone.now()
    if observe_clock(now):
        return {"blocked": True}
    with transaction.atomic():
        from .services import ensure_default_rules  # services import the engine

        ensure_default_rules()
        created = sum(
            GENERATORS[rule.trigger_kind](rule, now)
            for rule in AlertRule.objects.filter(is_active=True)
            if rule.trigger_kind in GENERATORS
        )
        result = {"created": created, "woke": _wake(now), "escalated": _escalate(now), "toasts": _notify(now)}
    return result
