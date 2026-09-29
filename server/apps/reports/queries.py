"""Report builders (V2 artboard 6.10 index). Read-only; all money in minor units."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from django.db.models import Max, OuterRef, Q, Subquery, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.audit import rules as audit_rules
from apps.audit import services as audit
from apps.billing.models import Folio, FolioLine, Payment
from apps.billing.services import balances_by_folio, balances_by_reservation, totals_by_folio
from apps.cash.models import Expense, ExpenseCategory, PaymentMethod, Shift
from apps.cash.services import ShiftTotals
from apps.core import arabic
from apps.core.errors import ApiError
from apps.core.models import HotelSettings
from apps.rooms.models import Room, RoomStatus, RoomStatusHistory, RoomType
from apps.stays import rules as stay_rules
from apps.stays.models import DurationKind, Reservation, ReservationStatus, Stay, StaySegment

from . import rules
from .framework import Column, Params, Report, report

# --- Optional filters (audit UI/UX §6.10): validated once, echoed in meta.filters for the screen and print ----


def _room_type(params: Params) -> RoomType | None:
    value = params.get("room_type")
    if not value:
        return None
    room_type = RoomType.objects.filter(pk=value).first() if _is_uuid(value) else None
    if room_type is None:
        raise ApiError("validation_error", 400, detail="نوع الغرفة غير موجود.")
    return room_type


def _is_uuid(value: str) -> bool:
    import uuid

    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


def _method(params: Params) -> str | None:
    value = params.get("method")
    if not value:
        return None
    if value not in PaymentMethod.values:
        raise ApiError("validation_error", 400, detail="طريقة الدفع غير معروفة.")
    return value


def _category(params: Params) -> str | None:
    value = params.get("expense_category")
    if not value:
        return None
    if value not in ExpenseCategory.values:
        raise ApiError("validation_error", 400, detail="فئة المصروف غير معروفة.")
    return value


def _filters(room_type: RoomType | None = None, method: str | None = None, category: str | None = None) -> list[dict]:
    out = []
    if room_type:
        out.append({"key": "room_type", "label": "نوع الغرفة", "value": room_type.name})
    if method:
        out.append({"key": "method", "label": "الطريقة", "value": PaymentMethod(method).label})
    if category:
        out.append({"key": "expense_category", "label": "الفئة", "value": ExpenseCategory(category).label})
    return out


def _start(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min))


def _days(params: Params) -> list[date]:
    return [params.date_from + timedelta(days=i) for i in range((params.date_to - params.date_from).days + 1)]


def _in_period(field: str, params: Params) -> Q:
    return Q(**{f"{field}__gte": _start(params.date_from), f"{field}__lt": _start(params.date_to + timedelta(days=1))})


def _range_text(r: Reservation) -> str:
    return f"{r.check_in_date:%d/%m} – {stay_rules.last_night(r.check_out_date):%d/%m}"


def _by(obj) -> str:
    return obj.created_by.full_name if obj.created_by_id and obj.created_by else ""


def _kind(kind: str) -> str:
    return DurationKind(kind).label


# --- Occupancy ------------------------------------------------------------------------------


def _occupied_rooms_by_night(days: list[date]) -> dict[date, set]:
    """Rooms with a stay in progress at midnight of each night (artboard 7.3 note).

    Only the segments that reach into the period are read, plus the open segment of every stay in progress (an
    overdue stay is still here tonight until checkout). Every segment since the first day, with a query each, took
    most of the owner dashboard's 80 s on five years of data (review 2026-09-29, F-1, F-4)."""
    today = timezone.localdate()
    first, last = days[0], days[-1]
    open_segment = {}
    for pk, stay_id in (
        StaySegment.objects.filter(stay__reservation__status=ReservationStatus.CHECKED_IN)
        .order_by("stay_id", "from_date", "created_at")
        .values_list("pk", "stay_id")
    ):
        open_segment[stay_id] = pk  # the stay's last segment wins
    open_ids = set(open_segment.values())
    nights = defaultdict(set)
    segments = StaySegment.objects.filter(from_date__lte=last).filter(Q(to_date__gt=first) | Q(pk__in=open_ids))
    for pk, room_id, from_date, end in segments.values_list("pk", "room_id", "from_date", "to_date"):
        if pk in open_ids:
            end = max(end, today + timedelta(days=1))
        d = max(from_date, first)
        while d < end and d <= last:
            nights[d].add(room_id)
            d += timedelta(days=1)
    return nights


def _maintenance_rooms_by_night(days: list[date]) -> dict[date, set]:
    """Rooms whose status at the end of the day was maintenance.

    Per room: the status before the period (else the first change's «from», else the status now), then the changes
    inside the period in order — not the whole history for every room and day (F-4)."""
    start, stop = _start(days[0]), _start(days[-1] + timedelta(days=1))
    history = RoomStatusHistory.objects.filter(room=OuterRef("pk"))
    rooms = (
        Room.objects.filter(in_service=True)
        .annotate(
            before=Subquery(history.filter(at__lt=start).order_by("-at").values("to_status")[:1]),
            first_after=Subquery(history.filter(at__gte=start).order_by("at").values("from_status")[:1]),
        )
        .values("pk", "status", "before", "first_after")
    )
    changes = defaultdict(list)
    for room_id, at, to_status in (
        RoomStatusHistory.objects.filter(at__gte=start, at__lt=stop)
        .order_by("at")
        .values_list("room_id", "at", "to_status")
    ):
        changes[room_id].append((at, to_status))
    result = defaultdict(set)
    for room in rooms:
        status = room["before"] or room["first_after"] or room["status"]
        events, i = changes.get(room["pk"], []), 0
        for day in days:
            end = _start(day + timedelta(days=1))
            while i < len(events) and events[i][0] < end:
                status = events[i][1]
                i += 1
            if status == RoomStatus.MAINTENANCE:
                result[day].add(room["pk"])
    return result


@report("occupancy", "الإشغال")
def occupancy(params: Params) -> Report:
    days = _days(params)
    available = Room.objects.filter(in_service=True).count()
    occupied = _occupied_rooms_by_night(days)
    maintenance = _maintenance_rooms_by_night(days)
    numbers = dict(Room.objects.values_list("pk", "number"))
    arrivals = defaultdict(int)
    for d in (
        Stay.objects.filter(_in_period("checked_in_at", params))
        .annotate(d=TruncDate("checked_in_at"))
        .values_list("d", flat=True)
    ):
        arrivals[d] += 1
    departures = defaultdict(int)
    for d in (
        Stay.objects.filter(_in_period("checked_out_at", params))
        .annotate(d=TruncDate("checked_out_at"))
        .values_list("d", flat=True)
    ):
        departures[d] += 1
    revenue = dict(
        FolioLine.objects.filter(_in_period("posted_at", params))
        .annotate(d=TruncDate("posted_at"))
        .values_list("d")
        .annotate(s=Sum("amount"))
    )
    collected = dict(
        Payment.objects.filter(_in_period("received_at", params))
        .annotate(d=TruncDate("received_at"))
        .values_list("d")
        .annotate(s=Sum("amount"))
    )
    rows = []
    for day in days:
        occ, maint = len(occupied[day]), len(maintenance[day])
        rows.append(
            {
                "day": day,
                "available": available - maint,
                "occupied": occ,
                "occupancy": rules.occupancy_percent(occ, available, maint),
                "arrivals": arrivals[day],
                "departures": departures[day],
                "revenue": revenue.get(day, 0),
                "collected": collected.get(day, 0),
                "maintenance": ", ".join(sorted(numbers[pk] for pk in maintenance[day])) or "—",
            }
        )
    n = len(rows)
    total_occ = sum(r["occupied"] for r in rows)
    total_avail = sum(r["available"] for r in rows)
    totals = {
        "available": round(total_avail / n, 1),
        "occupied": round(total_occ / n, 1),
        "occupancy": rules.percent(total_occ, total_avail),
        "arrivals": sum(r["arrivals"] for r in rows),
        "departures": sum(r["departures"] for r in rows),
        "revenue": sum(r["revenue"] for r in rows),
        "collected": sum(r["collected"] for r in rows),
    }
    return Report(
        "occupancy",
        "تقرير الإشغال",
        [
            Column("day", "اليوم", "date"),
            Column("available", "الغرف المتاحة", "int"),
            Column("occupied", "المشغولة", "int"),
            Column("occupancy", "الإشغال", "percent"),
            Column("arrivals", "الوصول", "int"),
            Column("departures", "المغادرة", "int"),
            Column("revenue", "الإيراد", "money"),
            Column("collected", "المحصّل", "money"),
            Column("maintenance", "صيانة"),
        ],
        rows,
        (params.date_from, params.date_to),
        totals=totals,
        formula=rules.OCCUPANCY_FORMULA,
        tiles=[
            {"label": "متوسط الإشغال", "value": totals["occupancy"], "type": "percent"},
            {"label": "الإيراد", "value": totals["revenue"], "type": "money"},
            {"label": "المحصّل", "value": totals["collected"], "type": "money"},
        ],
    )


# --- Arrivals and departures ---------------------------------------------------------------


@report("arrivals_departures", "الوصول والمغادرة", default_days=0)
def arrivals_departures(params: Params) -> Report:
    today = timezone.localdate()
    when = params.get("when", "today")
    room_type = _room_type(params)
    start = today + timedelta(days=1) if when == "tomorrow" else today
    end = start + timedelta(days=6 if when == "week" else 0)
    arrivals = Reservation.objects.filter(check_in_date__range=(start, end)).exclude(
        status=ReservationStatus.CHECKED_OUT
    )
    departures = Reservation.objects.filter(status=ReservationStatus.CHECKED_IN).filter(
        Q(check_out_date__range=(start + timedelta(days=1), end + timedelta(days=1)))
        | (Q(check_out_date__lte=today) if start == today else Q(pk__in=[]))
    )
    if room_type:
        arrivals = arrivals.filter(room_type=room_type)
        departures = departures.filter(room_type=room_type)
    rows, needs_prep = [], 0
    all_ids = [r.pk for r in arrivals] + [r.pk for r in departures]
    balances = balances_by_reservation(all_ids)
    for r in arrivals.select_related("guest", "room"):
        if r.status == ReservationStatus.CHECKED_IN:
            ready = "مسكّن"
        elif r.status in (ReservationStatus.CANCELLED, ReservationStatus.NO_SHOW):
            ready = ReservationStatus(r.status).label
        elif r.room_id:
            ready = RoomStatus(r.room.status).label
            needs_prep += r.room.status != RoomStatus.READY
        else:
            ready = "بلا غرفة"
        rows.append(
            {
                "move": "وصول",
                "room": r.room.number if r.room_id else "—",
                "guest": r.guest.full_name,
                "kind": _kind(r.duration_kind),
                "range": _range_text(r),
                "balance": balances.get(r.pk),
                "ready": ready,
                "status": r.status,
            }
        )
    for r in departures.select_related("guest", "room"):
        overdue = r.check_out_date <= today
        rows.append(
            {
                "move": "مغادرة",
                "room": r.room.number,
                "guest": r.guest.full_name,
                "kind": _kind(r.duration_kind),
                "range": _range_text(r) + (" (متجاوزة)" if overdue else ""),
                "balance": balances.get(r.pk),
                "ready": "—",
                "status": "overdue" if overdue else r.status,
            }
        )
    n_arr = sum(1 for r in rows if r["move"] == "وصول")
    out = Report(
        "arrivals_departures",
        "الوصول والمغادرة",
        [
            Column("move", "الحركة"),
            Column("room", "الغرفة"),
            Column("guest", "النزيل"),
            Column("kind", "النوع"),
            Column("range", "الفترة"),
            Column("balance", "المتبقي", "money"),
            Column("ready", "الغرفة جاهزة؟"),
        ],
        rows,
        (start, end),
        tiles=[
            {"label": "وصول اليوم" if when == "today" else "الوصول", "value": n_arr, "type": "int"},
            {"label": "مغادرة اليوم" if when == "today" else "المغادرة", "value": len(rows) - n_arr, "type": "int"},
            {"label": "غرف تحتاج تجهيزًا قبل الوصول", "value": needs_prep, "type": "int"},
        ],
        note="«جاهزة؟» تعكس حالة الغرفة الآن؛ الحجز المؤكد يظهر حتى لو لم يصل النزيل.",
    )
    out.filters = _filters(room_type)
    return out


# --- Guests in house / ending soon -----------------------------------------------------------


def _in_house():
    return (
        Reservation.objects.filter(status=ReservationStatus.CHECKED_IN)
        .select_related("guest", "room")
        .order_by("room__number")
    )


@report("current_guests", "النزلاء الحاليون", default_days=0)
def current_guests(params: Params) -> Report:
    today = timezone.localdate()
    room_type = _room_type(params)
    stays = list(_in_house().filter(room_type=room_type) if room_type else _in_house())
    balances = balances_by_reservation([r.pk for r in stays])
    rows = [
        {
            "room": r.room.number,
            "guest": r.guest.full_name,
            "phone": r.guest.phone,
            "kind": _kind(r.duration_kind),
            "range": _range_text(r),
            "days_left": (stay_rules.last_night(r.check_out_date) - today).days,
            "balance": balances.get(r.pk),
        }
        for r in stays
    ]
    out = Report(
        "current_guests",
        "النزلاء الحاليون",
        [
            Column("room", "الغرفة"),
            Column("guest", "النزيل"),
            Column("phone", "الهاتف"),
            Column("kind", "النوع"),
            Column("range", "الفترة"),
            Column("days_left", "الأيام المتبقية", "int"),
            Column("balance", "المتبقي", "money"),
        ],
        rows,
        tiles=[
            {"label": "مقيمون الآن", "value": len(rows), "type": "int"},
            {"label": "إجمالي المتبقي", "value": sum(r["balance"] or 0 for r in rows), "type": "money"},
        ],
    )
    out.filters = _filters(room_type)
    return out


def _ending_soon_count() -> int:
    today = timezone.localdate()
    return Reservation.objects.filter(status=ReservationStatus.CHECKED_IN, check_out_date__lte=today).count()


@report("ending_soon", "القريبة من الانتهاء والمتجاوزة", default_days=0, badge=_ending_soon_count)
def ending_soon(params: Params) -> Report:
    today = timezone.localdate()
    try:
        within = int(params.get("days", 3))
    except (TypeError, ValueError):
        raise ApiError("validation_error", 400, detail="عدد الأيام يجب أن يكون رقمًا.") from None
    stays = [r for r in _in_house() if (stay_rules.last_night(r.check_out_date) - today).days <= within]
    balances = balances_by_reservation([r.pk for r in stays])
    rows = []
    for r in sorted(stays, key=lambda r: r.check_out_date):
        left = (stay_rules.last_night(r.check_out_date) - today).days
        if left < 0:
            state = f"متجاوزة منذ {arabic.days(left)}"
        else:
            state = "تنتهي اليوم" if left == 0 else f"تنتهي بعد {arabic.days(left)}"
        rows.append(
            {
                "room": r.room.number,
                "guest": r.guest.full_name,
                "kind": _kind(r.duration_kind),
                "last_night": stay_rules.last_night(r.check_out_date),
                "state": state,
                "days_left": left,
                "balance": balances.get(r.pk),
            }
        )
    return Report(
        "ending_soon",
        "القريبة من الانتهاء والمتجاوزة",
        [
            Column("room", "الغرفة"),
            Column("guest", "النزيل"),
            Column("kind", "النوع"),
            Column("last_night", "آخر ليلة", "date"),
            Column("state", "الحالة"),
            Column("balance", "المتبقي", "money"),
        ],
        rows,
        tiles=[
            {"label": "متجاوزة", "value": sum(r["days_left"] < 0 for r in rows), "type": "int"},
            {"label": f"تنتهي خلال {within} أيام", "value": sum(r["days_left"] >= 0 for r in rows), "type": "int"},
        ],
    )


# --- Debts -----------------------------------------------------------------------------------


MAY_OWE = (
    ReservationStatus.CHECKED_IN,
    ReservationStatus.CHECKED_OUT,
    ReservationStatus.CANCELLED,  # nights used before cancelling still owed (review 2026-09-28, BIZ-6)
    ReservationStatus.NO_SHOW,
)


def _owing_ids() -> list:
    """Folios with a positive balance: balances without joins over every folio that may owe (F-1…F-3)."""
    balances = balances_by_folio(Folio.objects.filter(reservation__status__in=MAY_OWE))
    return [pk for pk, balance in balances.items() if balance > 0]


def _owing() -> dict:
    """folio id → full totals (discounts too) of the folios that owe only."""
    return totals_by_folio(Folio.objects.filter(pk__in=_owing_ids()))


def _debts():
    """(folio, totals) for every folio with a positive balance, newest invoice first."""
    owing = _owing()
    folios = Folio.objects.filter(pk__in=list(owing)).select_related(
        "reservation__guest", "reservation__room", "reservation__stay__override_by"
    )
    return [(folio, owing[folio.pk]) for folio in folios]


def _debt_count() -> int:
    return len(_owing_ids())


@report("debts", "الديون", badge=_debt_count)
def debts(params: Params) -> Report:
    today = timezone.localdate()
    status = params.get("status", "due")
    room_type = _room_type(params)
    rows = []
    if status in ("due", "all"):
        for folio, totals in _debts():
            r = folio.reservation
            if room_type and r.room_type_id != room_type.pk:
                continue
            stay = getattr(r, "stay", None)
            if r.status == ReservationStatus.CHECKED_IN:
                left = (stay_rules.last_night(r.check_out_date) - today).days
                age, age_days = "جارية", max(-left, 0)
                reason = f"متجاوزة منذ {arabic.days(left)}" if left < 0 else f"تنتهي بعد {arabic.days(left)}"
                if left < 0:
                    age = f"{arabic.days(left)} (جارية)"
            elif stay is None or stay.checked_out_at is None:
                # Cancelled or no-show before check-in, still owing (e.g. a service line): no stay to date it by
                # (review 2026-09-29, A-1 — this was a 500 on the report and the owner dashboard).
                age_days = (today - timezone.localtime(r.updated_at).date()).days
                age = arabic.days(age_days)
                reason = f"حجز {r.get_status_display()} بدين"
            else:
                age_days = (today - timezone.localtime(stay.checked_out_at).date()).days
                age = arabic.days(age_days)
                by = stay.override_by.full_name if stay.override_by_id else ""
                reason = f"خروج بتجاوز المدير ({by}) — «{stay.override_reason}»" if by else "خروج بدين"
            rows.append(
                {
                    "guest": r.guest.full_name,
                    "room": r.room.number if r.room_id else "—",
                    "range": _range_text(r),
                    "total": totals.total,
                    "paid": totals.paid,
                    "balance": totals.balance,
                    "age": age,
                    "age_days": age_days,
                    "reason": reason,
                    "state": "open" if r.status == "checked_in" else "after_checkout",
                }
            )
    if status in ("late", "all"):
        # Settled after checkout: grouped totals and last payment per folio, then only the matching stays are loaded
        # (two queries per departed guest before — 80 s for «all» on five years of data, F-3).
        departed = Folio.objects.filter(reservation__status=ReservationStatus.CHECKED_OUT)
        balances = balances_by_folio(departed)
        last_paid_of = dict(
            Payment.objects.filter(folio__in=departed.values("pk"))
            .order_by()
            .values_list("folio_id")
            .annotate(m=Max("received_at"))
        )
        late_ids = [
            stay_pk
            for stay_pk, folio_pk, out_at in Stay.objects.filter(
                reservation__status=ReservationStatus.CHECKED_OUT, checked_out_at__isnull=False
            ).values_list("pk", "reservation__folio", "checked_out_at")
            if balances.get(folio_pk) == 0 and last_paid_of.get(folio_pk) and last_paid_of[folio_pk] > out_at
        ]
        all_totals = totals_by_folio(Folio.objects.filter(reservation__stay__in=late_ids))
        for stay in Stay.objects.filter(pk__in=late_ids).select_related(
            "reservation__guest", "reservation__room", "reservation__folio"
        ):
            folio = stay.reservation.folio
            last_paid, totals = last_paid_of[folio.pk], all_totals[folio.pk]
            r = stay.reservation
            late = (timezone.localtime(last_paid).date() - timezone.localtime(stay.checked_out_at).date()).days
            rows.append(
                {
                    "guest": r.guest.full_name,
                    "room": r.room.number if r.room_id else "—",
                    "range": _range_text(r),
                    "total": totals.total,
                    "paid": totals.paid,
                    "balance": 0,
                    "age": f"سُدِّد بعد {arabic.days(late)}",
                    "age_days": late,
                    "reason": "مسدَّد متأخرًا",
                    "state": "paid_late",
                }
            )
    due = [r for r in rows if r["state"] != "paid_late"]
    open_ = [r for r in due if r["state"] == "open"]
    after = [r for r in due if r["state"] == "after_checkout"]
    month = Params(today.replace(day=1), today, {})
    charged = FolioLine.objects.filter(_in_period("posted_at", month)).aggregate(s=Sum("amount"))["s"] or 0
    collected = Payment.objects.filter(_in_period("received_at", month)).aggregate(s=Sum("amount"))["s"] or 0
    ages = [r["age_days"] for r in due]
    out = Report(
        "debts",
        "الديون",
        [
            Column("guest", "النزيل"),
            Column("room", "الغرفة"),
            Column("range", "الإقامة"),
            Column("total", "الإجمالي", "money"),
            Column("paid", "المدفوع", "money"),
            Column("balance", "المتبقي", "money"),
            Column("age", "عمر الدين"),
            Column("reason", "الحالة / السبب"),
        ],
        rows,
        totals={
            "total": sum(r["total"] for r in rows),
            "paid": sum(r["paid"] for r in rows),
            "balance": sum(r["balance"] for r in rows),
        },
        tiles=[
            {
                "label": "الديون المستحقة",
                "value": sum(r["balance"] for r in open_),
                "type": "money",
                "hint": f"{len(open_)} إقامات جارية",
            },
            {
                "label": "ديون بعد المغادرة",
                "value": sum(r["balance"] for r in after),
                "type": "money",
                "hint": f"{len(after)} نزلاء · خروج بتجاوز المدير",
            },
            {
                "label": "متوسط عمر الدين",
                "value": round(sum(ages) / len(ages)) if ages else 0,
                "type": "int",
                "hint": f"الأقدم {max(ages) if ages else 0} يومًا",
            },
            {
                "label": "نسبة التحصيل هذا الشهر",
                "value": rules.percent(collected, charged),
                "type": "percent",
                "hint": f"{collected // 100:,} من {charged // 100:,}",
            },
        ],
        note="يشمل الجاري وبعد المغادرة",
    )
    out.filters = _filters(room_type)
    return out


# --- Revenue and collection ------------------------------------------------------------------


@report("revenue", "الإيرادات والتحصيل")
def revenue(params: Params) -> Report:
    room_type, method = _room_type(params), _method(params)
    scope = Q(folio__reservation__room_type=room_type) if room_type else Q()
    lines = defaultdict(lambda: defaultdict(int))
    for d, kind, reversed_kind, s in (
        FolioLine.objects.filter(_in_period("posted_at", params), scope)
        .annotate(d=TruncDate("posted_at"))
        .values_list("d", "kind", "reverses__kind")
        .annotate(s=Sum("amount"))
    ):
        # A reversed discount is no discount (review 2026-09-29, A-16, as FolioTotals since BIZ-7).
        lines[d]["discount" if "discount" in (kind, reversed_kind) else kind] += s
    paid = defaultdict(lambda: defaultdict(int))
    for d, pay_method, currency, s in (
        Payment.objects.filter(_in_period("received_at", params), scope, **({"method": method} if method else {}))
        .annotate(d=TruncDate("received_at"))
        .values_list("d", "method", "currency")
        .annotate(s=Sum("amount"))
    ):
        # Money in other currencies has its own column (its pound value) so «نقدي» matches the shifts (A-8).
        paid[d]["foreign" if currency else pay_method] += s
    rows = []
    for day in _days(params):
        k, p = lines[day], paid[day]
        net = sum(k.values())
        rows.append(
            {
                "day": day,
                "charges": net - k["discount"],
                "discounts": k["discount"],
                "revenue": net,
                "cash": p["cash"],
                "bankak": p["bankak"],
                "transfer": p["transfer"],
                "foreign": p["foreign"],
                "collected": p["cash"] + p["bankak"] + p["transfer"] + p["foreign"],
            }
        )
    totals = {
        key: sum(r[key] for r in rows)
        for key in ("charges", "discounts", "revenue", "cash", "bankak", "transfer", "foreign", "collected")
    }
    return Report(
        "revenue",
        "الإيرادات والتحصيل",
        [
            Column("day", "اليوم", "date"),
            Column("charges", "الرسوم", "money"),
            Column("discounts", "الخصومات", "money"),
            Column("revenue", "صافي الإيراد", "money"),
            Column("cash", "نقدي", "money"),
            Column("bankak", "بنكك", "money"),
            Column("transfer", "تحويل", "money"),
            Column("foreign", "عملات أخرى (بالجنيه)", "money"),
            Column("collected", "المحصّل", "money"),
        ],
        rows,
        (params.date_from, params.date_to),
        totals=totals,
        tiles=[
            {"label": "صافي الإيراد", "value": totals["revenue"], "type": "money"},
            {"label": "المحصّل", "value": totals["collected"], "type": "money"},
            {
                "label": "نسبة التحصيل",
                "value": rules.percent(totals["collected"], totals["revenue"]),
                "type": "percent",
            },
        ],
        formula="الإيراد يُحتسب عند التسكين/التمديد؛ المحصّل عند استلام الدفعة (صافي بعد الردّ والعكس).",
        filters=_filters(room_type, method),
    )


# --- Expenses / cash --------------------------------------------------------------------------


@report("expenses", "المصروفات")
def expenses(params: Params) -> Report:
    threshold = HotelSettings.load().expense_attachment_threshold
    method, category = _method(params), _category(params)
    qs = (
        Expense.objects.filter(_in_period("spent_at", params))
        .select_related("created_by", "room")
        .prefetch_related("attachments")
    )
    if method:
        qs = qs.filter(method=method)
    if category:
        qs = qs.filter(category=category)
    rows = []
    by_cat = defaultdict(int)
    for e in qs.order_by("spent_at"):
        by_cat[e.get_category_display()] += e.amount
        rows.append(
            {
                "at": e.spent_at,
                "category": e.get_category_display(),
                "note": e.note if not e.reverses_id else f"تصحيح: {e.reason}",
                "amount": e.amount,
                "method": e.get_method_display(),
                "room": e.room.number if e.room_id else "",
                "attachment": "مرفق" if e.attachments.all() else ("ناقص" if e.amount > threshold else "—"),
                "by": _by(e),
            }
        )
    total = sum(r["amount"] for r in rows)
    top = max(by_cat.items(), key=lambda kv: kv[1]) if by_cat else ("—", 0)
    return Report(
        "expenses",
        "المصروفات",
        [
            Column("at", "التاريخ", "datetime"),
            Column("category", "الفئة"),
            Column("note", "البيان"),
            Column("amount", "المبلغ", "money"),
            Column("method", "الطريقة"),
            Column("room", "الغرفة"),
            Column("attachment", "مرفق"),
            Column("by", "بواسطة"),
        ],
        rows,
        (params.date_from, params.date_to),
        totals={"amount": total},
        tiles=[
            {"label": "إجمالي المصروفات", "value": total, "type": "money"},
            {"label": "أكبر فئة", "value": top[1], "type": "money", "hint": top[0]},
            {"label": "بانتظار مرفق", "value": sum(r["attachment"] == "ناقص" for r in rows), "type": "int"},
        ],
        note="المصروفات لا تُحذف — تُعكس بقيد مقابل مع سبب.",
        filters=_filters(method=method, category=category),
    )


def _shift_diff_count() -> int:
    week = timezone.now() - timedelta(days=7)
    return sum(1 for s in Shift.objects.filter(closed_at__gte=week) if s.difference)


@report("cash_shifts", "حركة الصندوق والورديات", default_days=6, badge=_shift_diff_count)
def cash_shifts(params: Params) -> Report:
    rows = []
    shifts = list(
        Shift.objects.filter(_in_period("opened_at", params))
        .select_related("created_by", "closed_by")
        .order_by("opened_at")
    )
    all_totals = ShiftTotals.for_shifts(shifts)  # three queries for the period, not three per shift (F-5)
    for s in shifts:
        t = all_totals[s.pk]
        opened, closed = timezone.localtime(s.opened_at), timezone.localtime(s.closed_at) if s.closed_at else None
        rows.append(
            {
                "date": opened.date(),
                "time": f"{opened:%H:%M} – {closed:%H:%M}" if closed else f"{opened:%H:%M} – مفتوحة",
                "user": _by(s),
                "opening": s.opening,
                "receipts": t.receipts["cash"],
                "expenses": t.expenses["cash"],
                "expected": s.expected if s.expected is not None else t.expected,
                "counted": s.counted,
                "difference": s.difference,
                "reason": s.difference_reason or "—",
            }
        )
    diffs = [r["difference"] for r in rows if r["difference"]]
    return Report(
        "cash_shifts",
        "حركة الصندوق والورديات",
        [
            Column("date", "التاريخ", "date"),
            Column("time", "الوقت"),
            Column("user", "المستخدم"),
            Column("opening", "الافتتاحي", "money"),
            Column("receipts", "المقبوضات", "money"),
            Column("expenses", "المصروفات", "money"),
            Column("expected", "المتوقع", "money"),
            Column("counted", "المعدود", "money"),
            Column("difference", "الفرق", "money"),
            Column("reason", "السبب"),
        ],
        rows,
        (params.date_from, params.date_to),
        formula=rules.CASH_FORMULA,
        tiles=[
            {"label": "الورديات", "value": len(rows), "type": "int"},
            {"label": "ورديات بفرق", "value": len(diffs), "type": "int"},
            {"label": "صافي الفروق", "value": sum(diffs), "type": "money"},
        ],
    )


# --- Adjustments, discounts, cancellations -----------------------------------------------------


@report("adjustments", "التعديلات والخصومات والإلغاءات")
def adjustments(params: Params) -> Report:
    rows = []

    def room_of(reservation):
        return reservation.room.number if reservation.room_id else "—"

    for line in FolioLine.objects.filter(
        _in_period("posted_at", params), kind__in=["discount", "reversal", "adjustment"]
    ).select_related("folio__reservation__room", "created_by"):
        label = {"discount": "خصم", "reversal": "عكس قيد", "adjustment": "تسوية"}[line.kind]
        rows.append(
            {
                "at": line.posted_at,
                "type": label,
                "text": line.description,
                "room": room_of(line.folio.reservation),
                "amount": line.amount,
                "by": _by(line),
                "reason": line.reason,
            }
        )
    # Discounts net of their reversals for the tile (A-16).
    net_discounts = (
        FolioLine.objects.filter(
            _in_period("posted_at", params), Q(kind="discount") | Q(kind="reversal", reverses__kind="discount")
        ).aggregate(s=Sum("amount"))["s"]
        or 0
    )
    for p in Payment.objects.filter(_in_period("received_at", params), kind__in=["reversal", "refund"]).select_related(
        "folio__reservation__room", "created_by"
    ):
        rows.append(
            {
                "at": p.received_at,
                "type": p.get_kind_display(),
                "text": p.receipt_label,
                "room": room_of(p.folio.reservation),
                "amount": p.amount,
                "by": _by(p),
                "reason": p.reason,
            }
        )
    for e in Expense.objects.filter(_in_period("spent_at", params), reverses__isnull=False).select_related(
        "created_by"
    ):
        rows.append(
            {
                "at": e.spent_at,
                "type": "عكس مصروف",
                "text": e.note,
                "room": "",
                "amount": e.amount,
                "by": _by(e),
                "reason": e.reason,
            }
        )
    for r in Reservation.objects.filter(
        _in_period("updated_at", params), status__in=["cancelled", "no_show"]
    ).select_related("room", "guest"):
        rows.append(
            {
                "at": r.updated_at,
                "type": ReservationStatus(r.status).label,
                "text": r.guest.full_name,
                "room": room_of(r),
                "amount": None,
                "by": "",
                "reason": r.status_reason,
            }
        )
    for s in Stay.objects.filter(_in_period("checked_out_at", params), override_by__isnull=False).select_related(
        "override_by", "reservation__room", "reservation__guest"
    ):
        rows.append(
            {
                "at": s.checked_out_at,
                "type": "تجاوز مدير",
                "text": s.reservation.guest.full_name,
                "room": room_of(s.reservation),
                "amount": None,
                "by": s.override_by.full_name,
                "reason": s.override_reason,
            }
        )
    for r in Reservation.objects.filter(_in_period("created_at", params)).select_related("room", "guest"):
        snap = r.rate_snapshot
        if snap.get("override_total") is None:  # JSON null is not SQL NULL, so filter here
            continue
        rows.append(
            {
                "at": r.created_at,
                "type": "سعر معدَّل",
                "text": f"{r.guest.full_name} — بدل {snap['base_total'] // 100:,}",
                "room": room_of(r),
                "amount": snap["override_total"] - snap["base_total"],
                "by": _by(r),
                "reason": snap.get("override_reason", ""),
            }
        )
    # Extensions priced by hand (review 2026-09-28, BIZ-3): the room line «تمديد … حتى dd/mm» dates each one.
    for line in FolioLine.objects.filter(
        _in_period("posted_at", params), kind="room", description__startswith="تمديد"
    ).select_related("folio__reservation__room", "folio__reservation__guest", "created_by"):
        r = line.folio.reservation
        for e in r.rate_snapshot.get("extensions", []):
            to = date.fromisoformat(e["to"])
            if (
                e.get("total") == e.get("base_total")
                or f"حتى {stay_rules.last_night(to):%d/%m}" not in line.description
            ):
                continue
            rows.append(
                {
                    "at": line.posted_at,
                    "type": "سعر تمديد معدَّل",
                    "text": f"{r.guest.full_name} — بدل {e['base_total'] // 100:,}",
                    "room": room_of(r),
                    "amount": e["total"] - e["base_total"],
                    "by": _by(line),
                    "reason": e.get("override_reason", ""),
                }
            )
    rows.sort(key=lambda r: r["at"])
    return Report(
        "adjustments",
        "التعديلات والخصومات والإلغاءات",
        [
            Column("at", "الوقت", "datetime"),
            Column("type", "النوع"),
            Column("text", "البيان"),
            Column("room", "الغرفة"),
            Column("amount", "المبلغ", "money"),
            Column("by", "بواسطة"),
            Column("reason", "السبب"),
        ],
        rows,
        (params.date_from, params.date_to),
        tiles=[
            {"label": "الخصومات", "value": -net_discounts, "type": "money"},
            {"label": "العكوس", "value": sum(r["type"].startswith("عكس") for r in rows), "type": "int"},
            {"label": "الإلغاءات", "value": sum(r["type"] in ("ملغى", "لم يحضر") for r in rows), "type": "int"},
        ],
    )


# --- Room states and vacancy ---------------------------------------------------------------------


@report("room_status", "حالة الغرف وفترات الخلو")
def room_status(params: Params) -> Report:
    days = _days(params)
    occupied = _occupied_rooms_by_night(days)
    maintenance = _maintenance_rooms_by_night(days)
    today = timezone.localdate()
    in_house = {r.room_id: r for r in _in_house()}
    rows = []
    for room in Room.objects.select_related("room_type").order_by("number"):
        stay = in_house.get(room.pk)
        status = RoomStatus(room.status).label
        if stay and stay.check_out_date <= today:
            status = "متجاوزة"
        busy = sum(room.pk in occupied[d] for d in days)
        maint = sum(room.pk in maintenance[d] for d in days)
        rows.append(
            {
                "room": room.number,
                "type": room.room_type.name,
                "status": status if room.in_service else "خارج الخدمة",
                "since": timezone.localtime(room.status_changed_at) if room.status_changed_at else None,
                "guest": stay.guest.full_name if stay else "",
                "occupied_nights": busy,
                "maintenance_nights": maint,
                "vacant_nights": len(days) - busy - maint if room.in_service else 0,
            }
        )
    return Report(
        "room_status",
        "حالة الغرف وفترات الخلو",
        [
            Column("room", "الغرفة"),
            Column("type", "النوع"),
            Column("status", "الحالة الآن"),
            Column("since", "منذ", "datetime"),
            Column("guest", "النزيل"),
            Column("occupied_nights", "ليالٍ مشغولة", "int"),
            Column("vacant_nights", "ليالٍ خالية", "int"),
            Column("maintenance_nights", "ليالي صيانة", "int"),
        ],
        rows,
        (params.date_from, params.date_to),
        totals={k: sum(r[k] for r in rows) for k in ("occupied_nights", "vacant_nights", "maintenance_nights")},
    )


# --- Alert response (needs the follow-up engine, phase B3) -------------------------------------------


def _neglected_count() -> int:
    from apps.followups.models import FollowupTask

    return FollowupTask.objects.filter(status="neglected").count()


@report("alert_response", "الاستجابة للتنبيهات", badge=_neglected_count)
def alert_response(params: Params) -> Report:
    """Who acted on each alert and how fast — the owner's accountability view."""
    from apps.followups.models import FollowupTask

    tasks = (
        FollowupTask.objects.filter(_in_period("due_at", params))
        .select_related("rule", "room", "shift__created_by")
        .prefetch_related("actions__created_by")
        .order_by("due_at")
    )
    rows, minutes = [], []
    for task in tasks:
        actions = list(task.actions.all())
        first = actions[0] if actions else None
        final = next((a for a in reversed(actions) if a.action in ("extend", "confirm_checkout", "done")), None)
        response = round((first.at - task.due_at).total_seconds() / 60) if first else None
        if response is not None:
            minutes.append(max(response, 0))
        rows.append(
            {
                "due_at": task.due_at,
                "title": task.title,
                "rule": task.rule.name,
                "first_action": first.get_action_display() if first else "—",
                "response_minutes": response,
                "snoozes": task.snooze_count,
                "final": final.get_action_display() if final else task.get_status_display(),
                "by": (final or first).created_by.full_name if (final or first) and (final or first).created_by else "",
                "neglected_shift": task.shift.created_by.full_name
                if task.neglected_at and task.shift_id and task.shift.created_by_id  # BIZ-9: even once superseded
                else "",
            }
        )
    neglected = sum(1 for r in rows if r["neglected_shift"])
    return Report(
        "alert_response",
        "الاستجابة للتنبيهات",
        [
            Column("due_at", "موعد التنبيه", "datetime"),
            Column("title", "التنبيه"),
            Column("rule", "القاعدة"),
            Column("first_action", "أول إجراء"),
            Column("response_minutes", "زمن الاستجابة (دقيقة)", "int"),
            Column("snoozes", "التأجيلات", "int"),
            Column("final", "النتيجة"),
            Column("by", "بواسطة"),
            Column("neglected_shift", "مُهمَلة — وردية"),
        ],
        rows,
        (params.date_from, params.date_to),
        tiles=[
            {"label": "التنبيهات", "value": len(rows), "type": "int"},
            {
                "label": "متوسط زمن الاستجابة (دقيقة)",
                "value": round(sum(minutes) / len(minutes)) if minutes else 0,
                "type": "int",
            },
            {"label": "مُهمَلة", "value": neglected, "type": "int"},
        ],
        note="كل إجراء مسجَّل باسم من نفّذه ووقته؛ المهمة المُهمَلة تُنسب إلى الوردية المسؤولة وقت الإهمال.",
    )


@report("audit_log", "سجل التدقيق", manager_only=True)
def audit_log(params: Params) -> Report:
    """Settings → سجل التدقيق «تصدير CSV»: the same filters as ``GET /audit/``."""
    category = params.get("category", "")
    if category and category not in audit_rules.CATEGORIES:
        raise ApiError("validation_error", 400, detail="تصنيف غير معروف.")
    rows = [
        {
            "seq": row.seq,
            "at": row.at,
            "by": row.actor.full_name if row.actor_id else "النظام",
            "category": audit_rules.CATEGORIES[audit_rules.category(row.action, row.after)],
            "action": row.action,
            "entity": row.entity,
            "entity_id": row.entity_id,
        }
        for row in audit.search(
            q=params.get("q", ""), date_from=params.date_from, date_to=params.date_to, category=category
        )
    ]
    return Report(
        "audit_log",
        "سجل التدقيق",
        [
            Column("seq", "#", "int"),
            Column("at", "الوقت", "datetime"),
            Column("by", "المستخدم"),
            Column("category", "التصنيف"),
            Column("action", "الإجراء"),
            Column("entity", "الكيان"),
            Column("entity_id", "المعرّف"),
        ],
        rows,
        period=(params.date_from, params.date_to),
        tiles=[{"label": "السجلات", "value": len(rows), "type": "int"}],
        note="السجل للقراءة فقط ومتسلسل بالبصمات؛ التحقق من السلسلة في «التحقق من السجل».",
    )
