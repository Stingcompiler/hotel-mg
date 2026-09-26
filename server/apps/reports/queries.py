"""Report builders (V2 artboard 6.10 index). Read-only; all money in minor units."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from django.db.models import Max, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.billing.models import Folio, FolioLine, Payment
from apps.billing.services import FolioTotals, balances_by_reservation
from apps.cash.models import Expense, Shift
from apps.cash.services import ShiftTotals
from apps.core.models import HotelSettings
from apps.rooms.models import Room, RoomStatus, RoomStatusHistory
from apps.stays import rules as stay_rules
from apps.stays.models import DurationKind, Reservation, ReservationStatus, Stay, StaySegment

from . import rules
from .framework import Column, Params, Report, report


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
    """Rooms with a stay in progress at midnight of each night (artboard 7.3 note)."""
    today = timezone.localdate()
    first, last = days[0], days[-1]
    nights = defaultdict(set)
    segments = StaySegment.objects.filter(from_date__lte=last).select_related("stay__reservation")
    for seg in segments:
        end = seg.to_date
        is_open = seg.stay.reservation.status == ReservationStatus.CHECKED_IN and seg == seg.stay.segments.last()
        if is_open:
            end = max(end, today + timedelta(days=1))  # overdue: still here tonight until checkout
        d = max(seg.from_date, first)
        while d < end and d <= last:
            nights[d].add(seg.room_id)
            d += timedelta(days=1)
    return nights


def _maintenance_rooms_by_night(days: list[date]) -> dict[date, set]:
    """Rooms whose status at the end of the day was maintenance."""
    history = defaultdict(list)
    for h in RoomStatusHistory.objects.order_by("at").values("room_id", "from_status", "to_status", "at"):
        history[h["room_id"]].append(h)
    result = defaultdict(set)
    for room in Room.objects.filter(in_service=True).values("pk", "status"):
        events = history.get(room["pk"], [])
        for day in days:
            end = _start(day + timedelta(days=1))
            before = [e for e in events if e["at"] < end]
            status = before[-1]["to_status"] if before else (events[0]["from_status"] if events else room["status"])
            if status == RoomStatus.MAINTENANCE:
                result[day].add(room["pk"])
    return result


@report("occupancy", "الإشغال")
def occupancy(params: Params) -> Report:
    days = _days(params)
    available = Room.objects.filter(in_service=True).count()
    occupied = _occupied_rooms_by_night(days)
    maintenance = _maintenance_rooms_by_night(days)
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
                "maintenance": ", ".join(
                    sorted(Room.objects.filter(pk__in=maintenance[day]).values_list("number", flat=True))
                )
                or "—",
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
    start = today + timedelta(days=1) if when == "tomorrow" else today
    end = start + timedelta(days=6 if when == "week" else 0)
    arrivals = Reservation.objects.filter(check_in_date__range=(start, end)).exclude(
        status=ReservationStatus.CHECKED_OUT
    )
    departures = Reservation.objects.filter(status=ReservationStatus.CHECKED_IN).filter(
        Q(check_out_date__range=(start + timedelta(days=1), end + timedelta(days=1)))
        | (Q(check_out_date__lte=today) if start == today else Q(pk__in=[]))
    )
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
    return Report(
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
    stays = list(_in_house())
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
    return Report(
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


def _ending_soon_count() -> int:
    today = timezone.localdate()
    return Reservation.objects.filter(status=ReservationStatus.CHECKED_IN, check_out_date__lte=today).count()


@report("ending_soon", "القريبة من الانتهاء والمتجاوزة", default_days=0, badge=_ending_soon_count)
def ending_soon(params: Params) -> Report:
    today = timezone.localdate()
    within = int(params.get("days", 3))
    stays = [r for r in _in_house() if (stay_rules.last_night(r.check_out_date) - today).days <= within]
    balances = balances_by_reservation([r.pk for r in stays])
    rows = []
    for r in sorted(stays, key=lambda r: r.check_out_date):
        left = (stay_rules.last_night(r.check_out_date) - today).days
        state = f"متجاوزة منذ {-left} يوم" if left < 0 else ("تنتهي اليوم" if left == 0 else f"تنتهي بعد {left} يوم")
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


def _debts():
    """(reservation, totals) for every folio with a positive balance."""
    folios = Folio.objects.select_related("reservation__guest", "reservation__room", "reservation__stay__override_by")
    out = []
    for folio in folios:
        totals = FolioTotals.of(folio)
        if totals.balance > 0 and folio.reservation.status in (
            ReservationStatus.CHECKED_IN,
            ReservationStatus.CHECKED_OUT,
        ):
            out.append((folio, totals))
    return out


def _debt_count() -> int:
    return len(_debts())


@report("debts", "الديون", badge=_debt_count)
def debts(params: Params) -> Report:
    today = timezone.localdate()
    status = params.get("status", "due")
    rows = []
    if status in ("due", "all"):
        for folio, totals in _debts():
            r = folio.reservation
            stay = getattr(r, "stay", None)
            if r.status == ReservationStatus.CHECKED_IN:
                left = (stay_rules.last_night(r.check_out_date) - today).days
                age, age_days = "جارية", max(-left, 0)
                reason = f"متجاوزة منذ {-left} يوم" if left < 0 else f"تنتهي بعد {left} يوم"
                if left < 0:
                    age = f"{-left} يوم (جارية)"
            else:
                age_days = (today - timezone.localtime(stay.checked_out_at).date()).days
                age = f"{age_days} يوم"
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
        for stay in Stay.objects.filter(reservation__status=ReservationStatus.CHECKED_OUT).select_related(
            "reservation__guest", "reservation__room", "reservation__folio"
        ):
            folio = stay.reservation.folio
            last_paid = folio.payments.aggregate(m=Max("received_at"))["m"]
            totals = FolioTotals.of(folio)
            if totals.balance == 0 and last_paid and stay.checked_out_at and last_paid > stay.checked_out_at:
                r = stay.reservation
                late = (timezone.localtime(last_paid).date() - timezone.localtime(stay.checked_out_at).date()).days
                rows.append(
                    {
                        "guest": r.guest.full_name,
                        "room": r.room.number,
                        "range": _range_text(r),
                        "total": totals.total,
                        "paid": totals.paid,
                        "balance": 0,
                        "age": f"سُدِّد بعد {late} يوم",
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
    return Report(
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


# --- Revenue and collection ------------------------------------------------------------------


@report("revenue", "الإيرادات والتحصيل")
def revenue(params: Params) -> Report:
    lines = defaultdict(lambda: defaultdict(int))
    for d, kind, s in (
        FolioLine.objects.filter(_in_period("posted_at", params))
        .annotate(d=TruncDate("posted_at"))
        .values_list("d", "kind")
        .annotate(s=Sum("amount"))
    ):
        lines[d][kind] += s
    paid = defaultdict(lambda: defaultdict(int))
    for d, method, s in (
        Payment.objects.filter(_in_period("received_at", params))
        .annotate(d=TruncDate("received_at"))
        .values_list("d", "method")
        .annotate(s=Sum("amount"))
    ):
        paid[d][method] += s
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
                "collected": p["cash"] + p["bankak"] + p["transfer"],
            }
        )
    totals = {
        key: sum(r[key] for r in rows)
        for key in ("charges", "discounts", "revenue", "cash", "bankak", "transfer", "collected")
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
    )


# --- Expenses / cash --------------------------------------------------------------------------


@report("expenses", "المصروفات")
def expenses(params: Params) -> Report:
    threshold = HotelSettings.load().expense_attachment_threshold
    qs = (
        Expense.objects.filter(_in_period("spent_at", params))
        .select_related("created_by", "room")
        .prefetch_related("attachments")
    )
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
    )


def _shift_diff_count() -> int:
    week = timezone.now() - timedelta(days=7)
    return sum(1 for s in Shift.objects.filter(closed_at__gte=week) if s.difference)


@report("cash_shifts", "حركة الصندوق والورديات", default_days=6, badge=_shift_diff_count)
def cash_shifts(params: Params) -> Report:
    rows = []
    for s in (
        Shift.objects.filter(_in_period("opened_at", params))
        .select_related("created_by", "closed_by")
        .order_by("opened_at")
    ):
        t = ShiftTotals.of(s)
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
            {"label": "الخصومات", "value": -sum(r["amount"] or 0 for r in rows if r["type"] == "خصم"), "type": "money"},
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
