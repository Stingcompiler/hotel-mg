"""Reservation use cases (spec §6.1, §6.2). Stay use cases (check-in and later) live in stay_services.py."""

from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.services import verify_manager_override
from apps.audit import services as audit
from apps.billing import rules as billing_rules
from apps.billing import services as billing
from apps.core.concurrency import get_for_update
from apps.core.errors import ApiError
from apps.core.models import HotelSettings
from apps.rooms.models import Room, RoomStatus, RoomType

from . import rules
from .models import Reservation, ReservationStatus

RESERVATION_FIELDS = [
    "guest",
    "room_type",
    "room",
    "check_in_date",
    "check_out_date",
    "duration_kind",
    "duration_count",
    "status",
    "total",
    "rate_snapshot",
    "notes",
    "status_reason",
]


def today() -> date:
    """Hotel-local date (settings.TIME_ZONE = Africa/Khartoum)."""
    return timezone.localdate()


def prices_of(room_type: RoomType) -> dict[str, int]:
    return {"nightly": room_type.nightly_price, "weekly": room_type.weekly_price, "monthly": room_type.monthly_price}


@dataclass(frozen=True)
class QuoteOption:
    key: str
    label: str
    formula: str
    units: dict
    duration_kind: str
    total: int


@dataclass(frozen=True)
class Quote:
    check_in_date: date
    check_out_date: date
    last_night: date
    nights: int
    options: list[QuoteOption]


def quote(room_type: RoomType, check_in_date: date, duration_kind: str, count: int) -> Quote:
    nights = rules.nights_for(duration_kind, count)
    if nights > rules.MAX_NIGHTS:
        raise ApiError("duration_too_long", 400)
    prices = prices_of(room_type)
    options = sorted(
        (
            QuoteOption(
                key=o.key,
                label=rules.option_label(o),
                formula=rules.option_formula(o, prices),
                units=o.units(),
                duration_kind=rules.duration_kind_of(o),
                total=rules.price(o, prices),
            )
            for o in rules.options_for(duration_kind, count)
        ),
        key=lambda o: o.total,
    )
    check_out = rules.check_out_for(check_in_date, nights)
    return Quote(check_in_date, check_out, rules.last_night(check_out), nights, options)


# --- Availability and overlap --------------------------------------------------------


def blocking_reservations(check_in: date, check_out: date, *, on_day: date | None = None):
    """Reservations that hold their room during [check_in, check_out) (spec §6.2).

    Checked-in stays keep blocking past their end date until checkout is recorded (overdue).
    """
    on_day = on_day or today()
    confirmed = Q(status=ReservationStatus.CONFIRMED, check_out_date__gt=check_in)
    # rules.blocking_until: a checked-in stay holds its room at least through today.
    if check_in <= on_day:
        held = Q(status=ReservationStatus.CHECKED_IN)
    else:
        held = Q(status=ReservationStatus.CHECKED_IN, check_out_date__gt=check_in)
    return Reservation.objects.filter(check_in_date__lt=check_out).filter(confirmed | held)


def available_rooms(room_type: RoomType | None, check_in: date, check_out: date):
    """In-service rooms free for the whole period; for arrivals today, not under maintenance."""
    busy = blocking_reservations(check_in, check_out).exclude(room=None).values("room_id")
    qs = Room.objects.filter(in_service=True).exclude(pk__in=busy)
    if room_type is not None:
        qs = qs.filter(room_type=room_type)
    if check_in <= today():
        qs = qs.exclude(status=RoomStatus.MAINTENANCE)
    return qs.select_related("room_type").order_by("number")


def check_type_capacity(room_type: RoomType, check_in: date, check_out: date) -> None:
    """Refuse a booking of ``room_type`` when every in-service room of the type is already taken on some night,
    counting bookings that have no room yet (review 2026-09-28, BIZ-8)."""
    RoomType.objects.select_for_update().filter(pk=room_type.pk).first()  # serialise bookings of one type
    on_day = today()
    held = [
        (r.check_in_date, rules.blocking_until(r.status, r.check_out_date, on_day))
        for r in blocking_reservations(check_in, check_out, on_day=on_day).filter(room_type=room_type)
    ]
    capacity = Room.objects.filter(room_type=room_type, in_service=True).count()
    if rules.peak_overlap(held, check_in, check_out) >= capacity:
        raise ApiError(
            "room_unavailable",
            409,
            detail=f"كل غرف «{room_type.name}» محجوزة في بعض ليالي هذه الفترة، ومنها حجوزات لم تُحدَّد غرفها بعد.",
        )


def lock_room_for(room: Room, check_in: date, check_out: date, *, exclude_pk=None) -> Room:
    """Lock the room row and refuse if another reservation holds it for the period."""
    room = Room.objects.select_for_update().get(pk=room.pk)  # row lock on PostgreSQL; IMMEDIATE txn on SQLite
    if not room.in_service:
        raise ApiError("room_unavailable", 409, detail=f"الغرفة {room.number} خارج الخدمة.")
    if check_in <= today() and room.status == RoomStatus.MAINTENANCE:
        raise ApiError("room_unavailable", 409, detail=f"الغرفة {room.number} في الصيانة.")
    clash = blocking_reservations(check_in, check_out).filter(room=room)
    if exclude_pk:
        clash = clash.exclude(pk=exclude_pk)
    if other := clash.select_related("guest").first():
        raise ApiError(
            "room_unavailable",
            409,
            detail=f"الغرفة {room.number} محجوزة من {other.check_in_date:%d/%m} إلى {other.check_out_date:%d/%m}.",
            conflict=str(other.pk),
        )
    return room


# --- Reservations ------------------------------------------------------------------


def snapshot(reservation: Reservation) -> dict:
    return audit.snapshot(reservation, RESERVATION_FIELDS)


@transaction.atomic
def create_reservation(
    actor,
    *,
    guest,
    room_type: RoomType,
    room: Room | None = None,
    check_in_date: date,
    duration_kind: str,
    count: int,
    option_key: str | None = None,
    final_total: int | None = None,
    override_reason: str = "",
    notes: str = "",
    discount: int = 0,
    discount_reason: str = "",
    deposit: int = 0,
    deposit_method: str = "cash",
    deposit_reference: str = "",
    manager_password: str = "",
    manager_reason: str = "",
    allow_past: bool = False,
) -> Reservation:
    """Book a room type (and optionally a room). Opens the folio; a deposit is taken in the open shift."""
    if check_in_date < today() and not allow_past:
        raise ApiError("date_in_past", 400)
    q = quote(room_type, check_in_date, duration_kind, count)
    options = {o.key: o for o in q.options}
    if option_key is None and len(options) == 1:
        option_key = next(iter(options))
    if option_key not in options:
        raise ApiError("pricing_choice_required", 400, options=list(options))
    option = options[option_key]

    base_total = option.total
    final_total = base_total if final_total is None else final_total
    override_reason = override_reason.strip()
    if rules.override_needs_reason(base_total, final_total) and not override_reason:
        raise ApiError("reason_required", 400, detail="سبب تعديل السعر مطلوب.")
    price_approver = approve_price(base_total, final_total, manager_password, manager_reason or override_reason)

    check_type_capacity(room_type, q.check_in_date, q.check_out_date)
    if room is not None:
        if room.room_type_id != room_type.pk:
            raise ApiError("room_type_mismatch", 400)
        room = lock_room_for(room, q.check_in_date, q.check_out_date)

    reservation = Reservation.objects.create(
        guest=guest,
        room_type=room_type,
        room=room,
        check_in_date=q.check_in_date,
        check_out_date=q.check_out_date,
        duration_kind=option.duration_kind,
        duration_count=q.nights if option.duration_kind == "mixed" else count,
        rate_snapshot={
            "room_type": room_type.name,
            "prices": prices_of(room_type),
            "option": option.key,
            "label": option.label,
            "units": option.units,
            "base_total": base_total,
            "override_total": final_total if final_total != base_total else None,
            "override_reason": override_reason if final_total != base_total else "",
            "override_approved_by": str(price_approver.pk) if price_approver else None,
        },
        total=final_total,
        notes=notes,
        created_by=actor,
    )
    folio = billing.open_folio(reservation, actor)
    if discount:
        _book_discount(reservation, discount, discount_reason, manager_password, manager_reason)
    audit.record(
        actor=actor,
        action="reservation.create",
        entity="reservation",
        entity_id=reservation.pk,
        after=snapshot(reservation),
    )
    if deposit:
        billing.take_payment(
            actor, folio, amount=deposit, method=deposit_method, reference=deposit_reference, kind="deposit"
        )
    return reservation


def approve_price(base_total: int, final_total: int, password: str, reason: str):
    """A price set below the base is a discount (review 2026-09-28, BIZ-3): within the hotel's limit anyone may give
    it with a reason; beyond it the manager's password is required. Returns the approving manager or None."""
    if final_total >= base_total:
        return None
    limit = HotelSettings.load().max_discount_percent
    if billing_rules.discount_within_limit(base_total - final_total, base_total, limit):
        return None
    if not password:
        raise ApiError(
            "override_required", 403, detail=f"السعر أقل من السعر الأساسي بأكثر من {limit}٪ ويحتاج موافقة المدير."
        )
    return verify_manager_override(password, reason)


def _book_discount(reservation: Reservation, discount: int, reason: str, manager_password: str, manager_reason: str):
    """Discount agreed at booking; posted with the room charge at check-in (artboard 6.4: «سبب الخصم *»)."""
    if discount < 0 or discount > reservation.total:
        raise ApiError("validation_error", 400, detail="قيمة الخصم غير صحيحة.")
    if not reason.strip():
        raise ApiError("reason_required", 400, detail="سبب الخصم مطلوب عند إدخال أي خصم.")
    approver = None
    limit = HotelSettings.load().max_discount_percent
    if not billing_rules.discount_within_limit(discount, reservation.total, limit):
        if not manager_password:
            raise ApiError("override_required", 403, detail=f"الخصم أكبر من {limit}٪ ويحتاج موافقة المدير.")
        approver = verify_manager_override(manager_password, manager_reason or reason)
    reservation.rate_snapshot["discount"] = {
        "amount": discount,
        "reason": reason.strip(),
        "approved_by": str(approver.pk) if approver else None,
    }
    reservation.save(update_fields=["rate_snapshot"])


def _get_locked(reservation_id, version: int | None) -> Reservation:
    return get_for_update(Reservation.objects, reservation_id, version)


@transaction.atomic
def cancel_reservation(actor, reservation_id, *, reason: str, version: int | None = None) -> Reservation:
    """Cancel a booking that has not been checked in. Cancelling a stay is a stay action."""
    reservation = _get_locked(reservation_id, version)
    if reservation.status != ReservationStatus.CONFIRMED:
        raise ApiError("invalid_reservation_status", 409)
    if not reason.strip():
        raise ApiError("reason_required", 400, detail="سبب الإلغاء مطلوب.")
    before = snapshot(reservation)
    reservation.status = ReservationStatus.CANCELLED
    reservation.status_reason = reason.strip()
    reservation.save()
    billing.close_folio(reservation)  # a deposit stays as credit until refunded
    audit.record(
        actor=actor,
        action="reservation.cancel",
        entity="reservation",
        entity_id=reservation.pk,
        before=before,
        after=snapshot(reservation),
    )
    return reservation


@transaction.atomic
def mark_no_show(actor, reservation_id, *, version: int | None = None) -> Reservation:
    reservation = _get_locked(reservation_id, version)
    if reservation.status != ReservationStatus.CONFIRMED:
        raise ApiError("invalid_reservation_status", 409)
    if reservation.check_in_date > today():
        raise ApiError("invalid_reservation_status", 409, detail="لا يمكن تسجيل عدم الحضور قبل تاريخ الوصول.")
    before = snapshot(reservation)
    reservation.status = ReservationStatus.NO_SHOW
    reservation.save()
    billing.close_folio(reservation)
    audit.record(
        actor=actor,
        action="reservation.no_show",
        entity="reservation",
        entity_id=reservation.pk,
        before=before,
        after=snapshot(reservation),
    )
    return reservation


@transaction.atomic
def assign_room(actor, reservation_id, room: Room, *, version: int | None = None) -> Reservation:
    reservation = _get_locked(reservation_id, version)
    if reservation.status != ReservationStatus.CONFIRMED:
        raise ApiError("invalid_reservation_status", 409)
    if room.room_type_id != reservation.room_type_id:
        raise ApiError("room_type_mismatch", 400)
    lock_room_for(room, reservation.check_in_date, reservation.check_out_date, exclude_pk=reservation.pk)
    before = snapshot(reservation)
    reservation.room = room
    reservation.save()
    audit.record(
        actor=actor,
        action="reservation.assign_room",
        entity="reservation",
        entity_id=reservation.pk,
        before=before,
        after=snapshot(reservation),
    )
    return reservation


def window(date_from: date, date_to: date):
    """Reservations touching [date_from, date_to) — the timeline view.

    A stay still checked in past its end (overdue) keeps occupying the room until check-out, so it is included.
    """
    return Reservation.objects.filter(check_in_date__lt=date_to).filter(
        Q(check_out_date__gt=date_from) | Q(status=ReservationStatus.CHECKED_IN)
    )
