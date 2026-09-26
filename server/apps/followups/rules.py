"""Alert timing and task state rules (spec §6.6, artboards 6.6 and 6.11). Pure functions, no ORM."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

OPEN_STATES = frozenset({"open", "snoozed", "waiting", "neglected"})
ACTIONS = ("extend", "confirm_checkout", "waiting", "snooze", "done")


def local_at(day: date, at: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, at, tzinfo=tz)


def first_alert_at(last_night: date, days_before: int, at: time, tz: ZoneInfo) -> datetime:
    """«قبل 5 أيام · 09:00» of a stay whose last night is ``last_night``."""
    return local_at(last_night - timedelta(days=days_before), at, tz)


def notification_times(
    due_at: datetime, second_at: datetime | None, repeat_hours: int, until: datetime
) -> list[datetime]:
    """When a still-open task should notify, up to ``until``: first alert, second alert, then every N hours.

    Repeats count from the latest scheduled alert (the second one if it exists).
    """
    times = [due_at]
    if second_at and second_at > due_at:
        times.append(second_at)
    if repeat_hours > 0:
        step = timedelta(hours=repeat_hours)
        t = times[-1] + step
        while t <= until:
            times.append(t)
            t += step
    return [t for t in times if t <= until]


def is_due(due_at: datetime, now: datetime) -> bool:
    return due_at <= now


def should_escalate(status: str, due_at: datetime, escalate_after_hours: int, now: datetime) -> bool:
    """A task still open this long after it fell due becomes «مُهمَلة» (spec §6.6)."""
    return status == "open" and escalate_after_hours > 0 and now >= due_at + timedelta(hours=escalate_after_hours)


def can_snooze(snooze_count: int, max_snoozes: int) -> bool:
    return snooze_count < max_snoozes


def snooze_label(snooze_count: int, max_snoozes: int) -> str:
    """«تأجيل (2 من 3)» (artboard 6.6)."""
    return f"تأجيل ({snooze_count} من {max_snoozes})"


def wakes_up(status: str, next_at: datetime | None, now: datetime) -> bool:
    """Snoozed or waiting tasks come back when their time arrives."""
    return status in ("snoozed", "waiting") and next_at is not None and next_at <= now


def when_text(last_night: date, today: date) -> str:
    """Due text for stays, shared by the list and the Windows toast title."""
    days = (last_night - today).days
    if days < 0:
        return "متجاوزة منذ يومين" if days == -2 else ("متجاوزة منذ يوم" if days == -1 else f"متجاوزة منذ {-days} أيام")
    if days == 0:
        return "تنتهي اليوم"
    if days == 1:
        return "تنتهي غدًا"
    if days == 2:
        return "تنتهي بعد يومين"
    return f"تنتهي بعد {days} {'أيام' if days <= 10 else 'يومًا'}"


def short_name(full_name: str) -> str:
    """Two words for the toast body («اسم من كلمتين»)."""
    return " ".join(full_name.split()[:2])


def toast_title(room_number: str, when: str) -> str:
    """«غرفة 305 — تنتهي بعد يومين», at most 40 characters (artboard 6.6 B)."""
    return f"غرفة {room_number} — {when}"[:40]


def toast_body(guest_name: str, kind_label: str) -> str:
    return f"{short_name(guest_name)} · {kind_label} · انقر للفتح"


def days_label(days: int) -> str:
    """Rule wording: «يوم النهاية», «قبل يوم», «قبل يومين», «قبل 5 أيام»."""
    if days == 0:
        return "يوم النهاية"
    if days == 1:
        return "قبل يوم"
    if days == 2:
        return "قبل يومين"
    return f"قبل {days} {'أيام' if days <= 10 else 'يومًا'}"
