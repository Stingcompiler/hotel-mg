"""Follow-up rules, task actions and the task board (spec §6.6, artboards 6.6 and 6.11)."""

from datetime import datetime, time

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.cash.services import current_shift
from apps.core.concurrency import get_for_update
from apps.core.errors import ApiError
from apps.core.hotel import current_hotel_id
from apps.stays import rules as stay_rules
from apps.stays import stay_services
from apps.stays.models import DurationKind, ReservationStatus

from . import engine, rules
from .models import AlertRule, FollowupTask, TaskAction, Toast, TriggerKind

TASK_FIELDS = ["status", "snooze_count", "next_at", "note", "due_at"]

DEFAULT_RULES = [
    # Artboard 6.11 rows + spec §6.6 defaults.
    {
        "name": "يومي",
        "trigger_kind": TriggerKind.STAY_ENDING,
        "duration_kind": "daily",
        "days_before": 0,
        "repeat_hours": 6,
    },
    {
        "name": "أسبوعي",
        "trigger_kind": TriggerKind.STAY_ENDING,
        "duration_kind": "weekly",
        "days_before": 2,
        "second_days_before": 0,
        "repeat_hours": 12,
    },
    {
        "name": "شهري",
        "trigger_kind": TriggerKind.STAY_ENDING,
        "duration_kind": "monthly",
        "days_before": 5,
        "second_days_before": 2,
        "repeat_hours": 12,
    },
    {"name": "إقامة متجاوزة", "trigger_kind": TriggerKind.STAY_OVERDUE, "repeat_hours": 24},
    {"name": "خروج بدين", "trigger_kind": TriggerKind.CHECKOUT_DEBT, "threshold": 0, "repeat_hours": 24},
    {
        "name": "وردية مفتوحة أكثر من 14 ساعة",
        "trigger_kind": TriggerKind.SHIFT_OPEN_TOO_LONG,
        "threshold_hours": 14,
        "repeat_hours": 2,
    },
    {
        "name": "تنظيف أكثر من 4 ساعات",
        "trigger_kind": TriggerKind.ROOM_CLEANING_TOO_LONG,
        "threshold_hours": 4,
        "repeat_hours": 4,
    },
    {
        "name": "صيانة أكثر من 7 أيام",
        "trigger_kind": TriggerKind.ROOM_MAINTENANCE_TOO_LONG,
        "threshold_hours": 168,
        "repeat_hours": 24,
    },
    {
        "name": "لا نسخة احتياطية منذ 24 ساعة",
        "trigger_kind": TriggerKind.NO_BACKUP,
        "threshold_hours": 24,
        "repeat_hours": 6,
    },
    {
        "name": "لا رفع إلى Drive منذ 3 أيام",
        "trigger_kind": TriggerKind.NO_DRIVE_UPLOAD,
        "threshold_hours": 72,
        "repeat_hours": 24,
    },
]


def ensure_default_rules() -> int:
    """Seed the default rules once per hotel (spec §6.6: «seeded on first run»)."""
    if settings.RUNTIME.hotel_id is None or AlertRule.objects.filter(hotel_id=current_hotel_id()).exists():
        return 0
    for row in DEFAULT_RULES:
        AlertRule.objects.create(**row)
    return len(DEFAULT_RULES)


# --- Stay hooks -------------------------------------------------------------------------------


def supersede_for_stay(stay, actor=None, reason: str = "", action: str = "") -> int:
    """Extension, room change, checkout or cancellation retire the stay's pending tasks (spec §6.6).

    The engine creates fresh ones from the new end date on its next tick. Nothing is deleted; a task that was
    neglected keeps ``neglected_at`` (reports count it from there). When the staff extended or checked the guest
    out from the stay screen (``action``), the alerts already due get that action recorded: it answered them
    (review 2026-09-28, BIZ-9, BIZ-12).
    """
    pending = FollowupTask.objects.filter(stay=stay, status__in=rules.OPEN_STATES)
    now, shift, count = timezone.now(), current_shift(), 0
    for task in pending:
        task.status = FollowupTask.Status.SUPERSEDED
        task.note = reason[:300]
        task.save(update_fields=["status", "note"])
        if action and rules.is_due(task.due_at, now):
            TaskAction.objects.create(
                task=task, action=action, at=now, note=reason[:300], shift=shift, created_by=actor
            )
        count += 1
    return count


# --- Actions ------------------------------------------------------------------------------------


def _record(actor, task: FollowupTask, action: str, *, note: str = "", next_at=None) -> TaskAction:
    shift = current_shift()
    row = TaskAction.objects.create(
        task=task, action=action, at=timezone.now(), note=note.strip(), next_at=next_at, shift=shift, created_by=actor
    )
    audit.record(
        actor=actor,
        action=f"followup.{action}",
        entity="followup_task",
        entity_id=task.pk,
        after={"task": task.title, "note": note.strip(), "next_at": next_at, "status": task.status},
    )
    return row


@transaction.atomic
def act(
    actor,
    task_id,
    action: str,
    *,
    note: str = "",
    until: datetime | None = None,
    version: int | None = None,
    stay_params: dict | None = None,
) -> FollowupTask:
    """Apply one of the four row buttons (artboard 6.6) or «تم». Only an action closes a task."""
    task = get_for_update(FollowupTask.objects.select_related("rule", "stay"), task_id, version)
    if task.status not in rules.OPEN_STATES:
        raise ApiError("task_closed", 409)
    now = timezone.now()

    if action in ("snooze", "waiting"):
        # Both postpone the alert: both count toward the rule's limit and neither goes past 36 hours (A-10).
        if not rules.can_snooze(task.snooze_count, task.rule.max_snoozes):
            raise ApiError("snooze_limit", 409, max_snoozes=task.rule.max_snoozes)
        if action == "waiting" and not note.strip():
            raise ApiError("reason_required", 400, detail="اكتب ما قاله النزيل.")
        if problem := rules.postpone_error(now, until):
            raise ApiError("validation_error", 400, detail=problem)
        task.snooze_count += 1
        if action == "snooze":
            task.status, task.next_at = FollowupTask.Status.SNOOZED, until
        else:
            task.status, task.next_at, task.note = FollowupTask.Status.WAITING, until, note.strip()
    elif action in ("extend", "confirm_checkout"):
        if task.stay_id is None or task.stay.reservation.status != ReservationStatus.CHECKED_IN:
            raise ApiError("invalid_reservation_status", 409)
        task.status = FollowupTask.Status.DONE
        task.save()
        _record(actor, task, action, note=note)
        if action == "extend":
            stay_services.extend(actor, task.stay_id, **(stay_params or {}))
        else:
            stay_services.checkout(actor, task.stay_id, **(stay_params or {}))
        return task
    elif action == "done":
        if not note.strip():
            raise ApiError("reason_required", 400, detail="اكتب ما تم.")
        task.status = FollowupTask.Status.DONE
    else:
        raise ApiError("validation_error", 400, detail="إجراء غير معروف.")
    task.save()
    _record(actor, task, action, note=note, next_at=until)
    return task


# --- Board ----------------------------------------------------------------------------------------


def _stay_row(stay, today) -> dict:
    r = stay.reservation
    last = stay_rules.last_night(r.check_out_date)
    return {
        "stay": stay.pk,
        "room": r.room.number,
        "room_state": "overdue" if r.check_out_date <= today else "occupied",
        "guest": r.guest.full_name,
        "kind": DurationKind(r.duration_kind).label,
        "last_night": last,
        "when": rules.when_text(last, today),
    }


def _rule_text(rule: AlertRule) -> str:
    if rule.trigger_kind == TriggerKind.STAY_ENDING:
        return f"قاعدة: {rule.name} – {rules.days_label(rule.days_before)} · {rule.at_time:%H:%M}"
    return f"قاعدة: {rule.name}"


def task_row(task: FollowupTask, today) -> dict:
    row = {
        "id": task.pk,
        "rule": _rule_text(task.rule),
        "trigger_kind": task.rule.trigger_kind,
        "title": task.title,
        "status": task.status,
        "due_at": task.due_at,
        "snooze_count": task.snooze_count,
        "max_snoozes": task.rule.max_snoozes,
        "snooze_label": rules.snooze_label(task.snooze_count, task.rule.max_snoozes),
        "can_snooze": rules.can_snooze(task.snooze_count, task.rule.max_snoozes),
        "next_at": task.next_at,
        "note": task.note,
        "neglected_shift_user": None,
        "version": task.version,
        "stay": None,
        "room": task.room.number if task.room_id else None,
    }
    if task.status == FollowupTask.Status.NEGLECTED and task.shift_id and task.shift.created_by_id:
        row["neglected_shift_user"] = task.shift.created_by.full_name
    if task.stay_id:
        row.update(_stay_row(task.stay, today))
    return row


def next_alert(stay, rules_by_kind: dict) -> tuple[datetime | None, AlertRule | None]:
    rule = rules_by_kind.get(engine._stay_kind(stay))
    if rule is None:
        return None, None
    due, _ = engine.stay_ending_due(rule, stay)
    return due, rule


def board(now: datetime | None = None, upcoming_days: int = 30) -> dict:
    """Groups of artboard 6.6: متأخرة / اليوم / القادمة, plus system tasks. One row per stay."""
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    pending = (
        FollowupTask.objects.filter(status__in=rules.OPEN_STATES)
        .select_related("rule", "shift__created_by", "room", "stay__reservation__room", "stay__reservation__guest")
        .order_by("-due_at")
    )
    late, due_today, system, seen = [], [], [], set()
    for task in pending:
        if task.stay_id is None:
            system.append(task_row(task, today))
            continue
        if task.stay_id in seen or task.stay.reservation.status != ReservationStatus.CHECKED_IN:
            continue
        seen.add(task.stay_id)
        row = task_row(task, today)
        (late if task.stay.reservation.check_out_date <= today else due_today).append(row)

    rules_by_kind = {
        r.duration_kind: r for r in AlertRule.objects.filter(trigger_kind=TriggerKind.STAY_ENDING, is_active=True)
    }
    upcoming = []
    for stay in engine._in_house():
        if stay.pk in seen:
            continue
        due, rule = next_alert(stay, rules_by_kind)
        if due and due > now and (due.date() - today).days <= upcoming_days:
            upcoming.append({**_stay_row(stay, today), "rule": _rule_text(rule), "alert_at": due})
    upcoming.sort(key=lambda r: r["alert_at"])
    late.sort(key=lambda r: r["last_night"])
    due_today.sort(key=lambda r: r["last_night"])
    last_action = TaskAction.objects.select_related("task", "created_by").order_by("-at").first()
    return {
        "counts": {"late": len(late), "today": len(due_today), "upcoming": len(upcoming), "system": len(system)},
        "late": late,
        "today": due_today,
        "upcoming": upcoming,
        "system": system,
        "last_action": {
            "text": f"{TaskAction.Action(last_action.action).label} · {last_action.task.title}",
            "by": last_action.created_by.full_name if last_action.created_by else "",
            "at": last_action.at,
        }
        if last_action
        else None,
    }


# --- Rules ----------------------------------------------------------------------------------------


RULE_FIELDS = [
    "name",
    "trigger_kind",
    "duration_kind",
    "days_before",
    "second_days_before",
    "at_time",
    "repeat_hours",
    "max_snoozes",
    "escalate_after_hours",
    "threshold_hours",
    "threshold",
    "windows_notification",
    "is_active",
]


@transaction.atomic
def update_rule(actor, rule_id, *, version: int, **changes) -> AlertRule:
    rule = get_for_update(AlertRule.objects, rule_id, version)
    before = audit.snapshot(rule, RULE_FIELDS)
    for field, value in changes.items():
        setattr(rule, field, value)
    rule.save()
    audit.record(
        actor=actor,
        action="followup.rule_update",
        entity="alert_rule",
        entity_id=rule.pk,
        before=before,
        after=audit.snapshot(rule, RULE_FIELDS),
    )
    return rule


@transaction.atomic
def create_rule(actor, **fields) -> AlertRule:
    rule = AlertRule.objects.create(created_by=actor, **fields)
    audit.record(
        actor=actor,
        action="followup.rule_create",
        entity="alert_rule",
        entity_id=rule.pk,
        after=audit.snapshot(rule, RULE_FIELDS),
    )
    return rule


def preview(rule_values: dict, last_night, now: datetime | None = None) -> dict:
    """Live preview of artboard 6.11: «إقامة شهرية تنتهي الجمعة 30 أكتوبر: التنبيه الأول … · تتأثر N إقامات»."""
    now = now or timezone.now()
    tz = engine._tz()
    at = rule_values.get("at_time") or time(9)
    first = rules.first_alert_at(last_night, rule_values.get("days_before", 0), at, tz)
    second = None
    if rule_values.get("second_days_before") is not None:
        second = rules.first_alert_at(last_night, rule_values["second_days_before"], at, tz)
    kind = rule_values.get("duration_kind")
    stays = [stay for stay in engine._in_house() if engine._stay_kind(stay) == kind] if kind else []
    stays.sort(key=lambda s: s.reservation.check_out_date)
    return {
        "last_night": last_night,
        "first_at": first,
        "second_at": second,
        "repeat_hours": rule_values.get("repeat_hours", 0),
        "affected_stays": len(stays),
        # The first few, soonest ending first, so the manager sees who the rule will wake (audit UI/UX §6).
        "stays": [
            {
                "room": s.reservation.room.number if s.reservation.room_id else "",
                "guest": s.reservation.guest.full_name,
                "last_night": stay_rules.last_night(s.reservation.check_out_date),
            }
            for s in stays[:8]
        ],
    }


def toasts_after(seq: int, limit: int = 20):
    return list(Toast.objects.filter(seq__gt=seq).order_by("seq")[:limit])


def summary_counts() -> dict:
    """For the login screen and the top bar badge (spec §10.4: tasks?status=open&count)."""
    b = board()
    return b["counts"]
