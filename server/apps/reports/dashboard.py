"""Owner dashboard data (artboard 6.12, spec §10.4 ``reports/owner-dashboard``). Read-only."""

from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Sum
from django.utils import timezone

from apps.billing.models import FolioLine, Payment
from apps.cash.models import Shift
from apps.core import arabic
from apps.core.models import HotelSettings
from apps.followups import rules as followup_rules
from apps.followups.models import FollowupTask
from apps.rooms.models import Room
from apps.stays import rules as stay_rules
from apps.stays.models import ReservationStatus

from . import rules
from .framework import Params
from .queries import _debts, _in_house, _in_period, _maintenance_rooms_by_night, _occupied_rooms_by_night


def _room_number(reservation) -> str:
    """A cancelled or no-show booking may owe money without ever having had a room (A-1)."""
    return reservation.room.number if reservation.room_id else "—"


def _sum(qs, field="amount") -> int:
    return qs.aggregate(s=Sum(field))["s"] or 0


def _occupancy_series(days: list[date]) -> list[dict]:
    available = Room.objects.filter(in_service=True).count()
    occupied = _occupied_rooms_by_night(days)
    maintenance = _maintenance_rooms_by_night(days)
    return [
        {
            "date": d,
            "occupied": len(occupied[d]),
            "rooms": available,
            "available": available - len(maintenance[d]),  # room-nights for the period average
            "percent": rules.occupancy_percent(len(occupied[d]), available, len(maintenance[d])),
        }
        for d in days
    ]


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _weeks(start: date, end: date) -> list[dict]:
    """Revenue vs collected per week of the period (1–7, 8–14, 15–21, 22–end)."""
    one_month = (start.year, start.month) == (end.year, end.month)
    weeks, cursor, n = [], start, 1
    while cursor <= end:
        stop = min(cursor + timedelta(days=6), end)
        p = Params(cursor, stop, {})
        weeks.append(
            {
                "label": rules.week_label(n, cursor, stop, one_month),
                "date_from": cursor,
                "date_to": stop,
                "revenue": _sum(FolioLine.objects.filter(_in_period("posted_at", p))),
                "collected": _sum(Payment.objects.filter(_in_period("received_at", p))),
            }
        )
        cursor, n = stop + timedelta(days=1), n + 1
    return weeks


def _attention(today: date, debt_limit: int, month: Params) -> list[dict]:
    items = []
    for r in _in_house():
        if r.check_out_date <= today:
            days = (today - stay_rules.last_night(r.check_out_date)).days
            items.append(
                {
                    "kind": "overdue",
                    "label": "متجاوزة",
                    "report": "ending_soon",
                    "text": f"غرفة {r.room.number} · {r.guest.full_name} · متجاوزة منذ {arabic.days(days)}",
                }
            )
    for task in FollowupTask.objects.filter(status="neglected").select_related("shift__created_by", "room"):
        who = task.shift.created_by.full_name if task.shift_id and task.shift.created_by_id else "—"
        items.append(
            {
                "kind": "neglected",
                "label": "تنبيه مُهمَل",
                "report": "alert_response",
                "text": f"{task.title} — وردية {who}",
            }
        )
    for folio, totals in _debts():
        if totals.balance > debt_limit:
            r = folio.reservation
            items.append(
                {
                    "kind": "debt",
                    "label": "دين",
                    "report": "debts",
                    "text": f"دين فوق الحد ({rules.pounds_text(debt_limit)}): غرفة {_room_number(r)} · "
                    f"{rules.pounds_text(totals.balance)} ج.س",
                }
            )
    for shift in Shift.objects.filter(_in_period("closed_at", month)).select_related("created_by"):
        if shift.difference:
            items.append(
                {
                    "kind": "shift",
                    "label": "فرق وردية",
                    "report": "cash_shifts",
                    "text": f"وردية {shift.created_by.full_name if shift.created_by_id else '—'} "
                    f"{timezone.localtime(shift.opened_at):%d/%m} · فرق {rules.pounds_text(shift.difference)} ج.س",
                }
            )
    for room in Room.objects.filter(status="maintenance", in_service=True, status_changed_at__isnull=False):
        days = (today - timezone.localtime(room.status_changed_at).date()).days
        items.append(
            {
                "kind": "maint",
                "label": "صيانة طويلة" if days >= 7 else "صيانة",
                "report": "room_status",
                "text": f"غرفة {room.number} في الصيانة منذ {arabic.days(days)} ({room.maintenance_reason})",
            }
        )
    return items


def _staff_response(month: Params) -> list[dict]:
    """Per employee: alerts that fell due in their shift, handled with an explicit action, neglected, delay.

    Delay = alert time → first explicit action (extend / confirm departure / awaiting reply / done);
    a snooze is not an action (artboard 6.12 note). An alert that fell due while no shift was open (the
    midnight alerts before the morning shift) belongs to the next shift that opened: it was waiting for them.
    """
    shifts = list(Shift.objects.select_related("created_by").order_by("opened_at"))
    windows = [(s.pk, s.opened_at, s.closed_at) for s in shifts]
    names = {s.pk: (s.created_by.full_name if s.created_by_id else "—") for s in shifts}

    def owner_of(when):
        return names.get(followup_rules.responsible_shift(windows, when))  # the engine's rule too (BIZ-10)

    stats = defaultdict(lambda: {"total": 0, "handled": 0, "neglected": 0, "delays": []})
    for task in FollowupTask.objects.filter(_in_period("due_at", month)).prefetch_related("actions"):
        name = owner_of(task.due_at)
        if name is None:
            continue
        row = stats[name]
        row["total"] += 1
        explicit = [a for a in task.actions.all() if a.action != "snooze"]
        if explicit:
            row["handled"] += 1
            row["delays"].append(max((explicit[0].at - task.due_at).total_seconds() / 60, 0))
        if task.neglected_at:
            row["neglected"] += 1
    return [
        {
            "name": name,
            "total": s["total"],
            "handled": s["handled"],
            "handled_percent": rules.percent(s["handled"], s["total"]),
            "neglected": s["neglected"],
            "average_delay_minutes": round(sum(s["delays"]) / len(s["delays"])) if s["delays"] else None,
        }
        for name, s in sorted(stats.items(), key=lambda kv: -kv[1]["total"])
    ]


def owner_dashboard(period: str = "month") -> dict:
    today = timezone.localdate()
    start, end = rules.dashboard_period(period, today)
    label = rules.PERIOD_LABELS[period]
    month = Params(start, end, {})
    settings_row = HotelSettings.load()

    revenue = _sum(FolioLine.objects.filter(_in_period("posted_at", month)))
    collected = _sum(Payment.objects.filter(_in_period("received_at", month)))
    prev_start, prev_end = rules.comparison_period(period, start, end)
    prev_revenue = _sum(FolioLine.objects.filter(_in_period("posted_at", Params(prev_start, prev_end, {}))))

    series = _occupancy_series(_days(today - timedelta(days=29), today))
    tonight = series[-1]
    # The period average covers every night of the selected period, not the chart's last 30 nights.
    in_period = _occupancy_series(_days(start, end))
    debts = [(folio, totals) for folio, totals in _debts()]
    largest = max(debts, key=lambda d: d[1].balance) if debts else None
    neglected = (
        FollowupTask.objects.filter(status="neglected").select_related("shift__created_by").order_by("-neglected_at")
    )
    latest = neglected.first()

    kpis = {
        "occupancy_today": {
            "value": tonight["percent"],
            "occupied": tonight["occupied"],
            "rooms": tonight["rooms"],
            "period_average": rules.percent(
                sum(p["occupied"] for p in in_period), sum(p["available"] for p in in_period)
            ),
        },
        "revenue": {
            "value": revenue,
            "change_percent": rules.percent(revenue - prev_revenue, prev_revenue) if prev_revenue else None,
        },
        "collected": {"value": collected, "of_revenue_percent": rules.percent(collected, revenue)},
        "debts": {
            "value": sum(t.balance for _, t in debts),
            "count": len(debts),
            "largest": (
                {"room": _room_number(largest[0].reservation), "amount": largest[1].balance} if largest else None
            ),
        },
        "neglected_alerts": {
            "value": neglected.count(),
            "latest_shift_user": latest.shift.created_by.full_name
            if latest and latest.shift_id and latest.shift.created_by_id
            else None,
            "latest_at": latest.neglected_at if latest else None,
        },
    }
    peak = max(series, key=lambda p: p["percent"])
    return {
        "period": {"key": period, "label": label, "date_from": start, "date_to": end},
        "rooms": Room.objects.filter(in_service=True).count(),
        "kpis": kpis,
        "occupancy": {
            "series": series,
            "average": round(sum(p["percent"] for p in series) / len(series)),
            "peak": {"date": peak["date"], "percent": peak["percent"]},
        },
        "weeks": _weeks(start, end),
        "attention": _attention(today, settings_row.debt_attention_threshold, month),
        "staff": _staff_response(month),
        "overdue_stays": sum(
            1 for r in _in_house() if r.status == ReservationStatus.CHECKED_IN and r.check_out_date <= today
        ),
    }
