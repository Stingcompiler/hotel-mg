"""Stay use cases: check-in, extend, change room, checkout, cancel (spec §6.1-§6.4).

Each posts its folio lines (room charge, extension, room-change difference, cancellation settlement).
Follow-up task supersession arrives with the alert engine in B3.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.services import verify_manager_override
from apps.audit import services as audit
from apps.billing import rules as billing_rules
from apps.billing import services as billing
from apps.billing.models import Folio
from apps.core.concurrency import get_for_update
from apps.core.errors import ApiError
from apps.rooms import services as room_services
from apps.rooms.models import Room, RoomStatus, RoomType

from . import rules
from .models import Reservation, ReservationStatus, Stay, StaySegment
from .services import available_rooms, create_reservation, lock_room_for, prices_of, quote, snapshot, today


def _stay_for_update(stay_id, version: int | None) -> Stay:
    stay = get_for_update(Stay.objects.select_related("reservation"), stay_id, version)
    if stay.reservation.status != ReservationStatus.CHECKED_IN:
        raise ApiError("invalid_reservation_status", 409)
    return stay


def _retire_tasks(stay: Stay, reason: str) -> None:
    """Pending follow-up tasks of the stay become superseded; the engine re-plans from the new end (spec §6.6)."""
    from apps.followups.services import supersede_for_stay  # followups depends on stays; import at use

    supersede_for_stay(stay, reason=reason)


def _open_segment(stay: Stay) -> StaySegment:
    return stay.segments.order_by("-from_date", "-created_at").first()


def _leave_room(room: Room, choice: str, maintenance_reason: str, actor, why: str) -> None:
    """Vacated room: occupied → cleaning (→ maintenance if chosen)."""
    room = Room.objects.select_for_update().get(pk=room.pk)
    for step in rules.after_room_statuses(choice):
        trigger = "checkout" if step == "cleaning" else "manual"
        room_services.transition(
            room, step, trigger=trigger, actor=actor, reason=maintenance_reason if step == "maintenance" else why
        )


# --- Check-in -------------------------------------------------------------------------


def record_check_in(actor, reservation: Reservation, room: Room, at=None) -> Stay:
    """Occupy the room and open the stay. No date validation: callers check the rules."""
    room = Room.objects.select_for_update().get(pk=room.pk)
    room_services.transition(
        room, RoomStatus.OCCUPIED, trigger="check_in", actor=actor, reason=reservation.guest.full_name
    )
    reservation.room = room
    reservation.status = ReservationStatus.CHECKED_IN
    reservation.save()
    stay = Stay.objects.create(reservation=reservation, checked_in_at=at or timezone.now(), created_by=actor)
    StaySegment.objects.create(
        stay=stay, room=room, from_date=reservation.check_in_date, to_date=reservation.check_out_date, created_by=actor
    )
    folio = billing.folio_of(reservation)
    snap = reservation.rate_snapshot
    billing.post_line(
        actor,
        folio,
        kind="room",
        description=rules.room_line_text(
            reservation.duration_kind,
            reservation.room_type.name,
            room.number,
            reservation.nights,
            snap.get("label", ""),
        ),
        amount=reservation.total,
        reason=snap.get("override_reason", ""),
    )
    if discount := snap.get("discount"):
        billing.post_line(
            actor,
            folio,
            kind="discount",
            description=f"خصم: {discount['reason']}",
            amount=-discount["amount"],
            reason=discount["reason"],
        )
    return stay


@transaction.atomic
def check_in(actor, reservation_id, *, room: Room | None = None, version: int | None = None) -> Stay:
    reservation = get_for_update(Reservation.objects.select_related("guest"), reservation_id, version)
    if reservation.status != ReservationStatus.CONFIRMED:
        raise ApiError("invalid_reservation_status", 409)
    if not rules.can_check_in(reservation.check_in_date, reservation.check_out_date, today()):
        raise ApiError("check_in_not_allowed", 409)
    room = room or reservation.room
    if room is None:
        raise ApiError("room_required", 400)
    if room.room_type_id != reservation.room_type_id:
        raise ApiError("room_type_mismatch", 400)
    room = lock_room_for(room, today(), reservation.check_out_date, exclude_pk=reservation.pk)
    if room.status != RoomStatus.READY:
        raise ApiError("room_not_ready", 409, detail=f"الغرفة {room.number} «{RoomStatus(room.status).label}».")
    before = snapshot(reservation)
    stay = record_check_in(actor, reservation, room)
    audit.record(
        actor=actor,
        action="stay.check_in",
        entity="stay",
        entity_id=stay.pk,
        before=before,
        after=snapshot(reservation),
    )
    return stay


@transaction.atomic
def book_and_check_in(actor, **booking) -> Stay:
    """Walk-in: «تسكين الآن» on the booking form — reservation and check-in in one transaction."""
    reservation = create_reservation(actor, **booking)
    return check_in(actor, reservation.pk)


# --- Extend ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtensionQuote:
    current_check_out: object
    quote: object
    total_nights: int
    room_available: bool


def extension_quote(stay: Stay, duration_kind: str, count: int) -> ExtensionQuote:
    reservation = stay.reservation
    q = quote(reservation.room_type, reservation.check_out_date, duration_kind, count)
    clash = (
        Reservation.objects.filter(room=reservation.room, status__in=rules.BLOCKING_STATUSES)
        .exclude(pk=reservation.pk)
        .filter(check_in_date__lt=q.check_out_date, check_out_date__gt=reservation.check_out_date)
        .exists()
    )
    total = (q.check_out_date - reservation.check_in_date).days
    return ExtensionQuote(reservation.check_out_date, q, total, not clash)


@transaction.atomic
def extend(
    actor,
    stay_id,
    *,
    duration_kind: str,
    count: int,
    option_key: str | None = None,
    final_total: int | None = None,
    override_reason: str = "",
    version: int | None = None,
) -> Stay:
    """Add nights after the current end, priced at today's rates for the room type (artboard 6.5 D)."""
    stay = _stay_for_update(stay_id, version)
    reservation = stay.reservation
    q = quote(reservation.room_type, reservation.check_out_date, duration_kind, count)
    options = {o.key: o for o in q.options}
    if option_key is None and len(options) == 1:
        option_key = next(iter(options))
    if option_key not in options:
        raise ApiError("pricing_choice_required", 400, options=list(options))
    option = options[option_key]
    final_total = option.total if final_total is None else final_total
    if rules.override_needs_reason(option.total, final_total) and not override_reason.strip():
        raise ApiError("reason_required", 400, detail="سبب تعديل السعر مطلوب.")
    lock_room_for(reservation.room, reservation.check_out_date, q.check_out_date, exclude_pk=reservation.pk)

    before = snapshot(reservation)
    old_out = reservation.check_out_date
    same_kind = option.duration_kind == reservation.duration_kind != "mixed"
    reservation.duration_count = (
        reservation.duration_count + count if same_kind else (q.check_out_date - reservation.check_in_date).days
    )
    reservation.duration_kind = reservation.duration_kind if same_kind else "mixed"
    reservation.check_out_date = q.check_out_date
    reservation.total += final_total
    reservation.rate_snapshot.setdefault("extensions", []).append(
        {
            "from": old_out.isoformat(),
            "to": q.check_out_date.isoformat(),
            "option": option.key,
            "label": option.label,
            "prices": prices_of(reservation.room_type),
            "base_total": option.total,
            "total": final_total,
            "override_reason": override_reason.strip(),
        }
    )
    reservation.save()
    segment = _open_segment(stay)
    segment.to_date = q.check_out_date
    segment.save()
    _retire_tasks(stay, f"تمديد حتى {rules.last_night(q.check_out_date):%d/%m}")
    billing.post_line(
        actor,
        billing.folio_of(reservation),
        kind="room",
        description=f"تمديد — {option.label} حتى {rules.last_night(q.check_out_date):%d/%m}",
        amount=final_total,
        reason=override_reason,
    )
    audit.record(
        actor=actor, action="stay.extend", entity="stay", entity_id=stay.pk, before=before, after=snapshot(reservation)
    )
    return stay


# --- Change room ----------------------------------------------------------------------


def change_room_difference(stay: Stay, new_type: RoomType) -> int:
    reservation = stay.reservation
    if new_type.pk == reservation.room_type_id:
        return 0
    units = reservation.rate_snapshot.get("units") or {}
    option = rules.Option(units.get("monthly", 0), units.get("weekly", 0), units.get("daily", 0))
    if option.nights == 0:  # snapshot without units (e.g. migrated data): price by nights
        option = rules.Option(0, 0, reservation.nights)
    old_total = rules.price(option, reservation.rate_snapshot.get("prices") or prices_of(reservation.room_type))
    new_total = rules.price(option, prices_of(new_type))
    remaining = rules.remaining_nights(reservation.check_out_date, today())
    return rules.room_change_difference(old_total, new_total, remaining, option.nights)


def change_room_candidates(stay: Stay):
    """Ready rooms free for the rest of the stay, same type first (V2 artboard 6.5 E)."""
    reservation = stay.reservation
    end = max(reservation.check_out_date, today() + timedelta(days=1))
    rooms = [
        r for r in available_rooms(None, today(), end) if r.status == RoomStatus.READY and r.pk != reservation.room_id
    ]
    rooms.sort(key=lambda r: (r.room_type_id != reservation.room_type_id, r.number))
    return [(room, change_room_difference(stay, room.room_type)) for room in rooms]


@transaction.atomic
def change_room(
    actor,
    stay_id,
    *,
    room: Room,
    reason: str,
    old_room_status: str = "cleaning",
    maintenance_reason: str = "",
    override_password: str = "",
    override_reason: str = "",
    version: int | None = None,
) -> Stay:
    """Move the guest from today. Negative price difference needs a manager (V2 artboard 6.5 E)."""
    if not reason.strip():
        raise ApiError("reason_required", 400, detail="سبب التغيير مطلوب.")
    stay = _stay_for_update(stay_id, version)
    reservation = stay.reservation
    if room.pk == reservation.room_id:
        raise ApiError("room_unavailable", 409, detail="الغرفة الجديدة هي الغرفة الحالية.")
    end = max(reservation.check_out_date, today() + timedelta(days=1))
    new_room = lock_room_for(room, today(), end, exclude_pk=reservation.pk)
    if new_room.status != RoomStatus.READY:
        raise ApiError("room_not_ready", 409, detail=f"الغرفة {new_room.number} «{RoomStatus(new_room.status).label}».")
    difference = change_room_difference(stay, new_room.room_type)
    approver = None
    if difference < 0:
        if not override_password:
            raise ApiError("override_required", 403, difference=difference)
        approver = verify_manager_override(override_password, override_reason)

    before = snapshot(reservation)
    old_room = reservation.room
    segment = _open_segment(stay)
    segment.to_date = max(today(), segment.from_date)
    segment.save()
    StaySegment.objects.create(
        stay=stay, room=new_room, from_date=today(), to_date=end, reason=reason.strip(), created_by=actor
    )
    _leave_room(old_room, old_room_status, maintenance_reason, actor, f"نقل النزيل إلى {new_room.number}")
    room_services.transition(
        new_room, RoomStatus.OCCUPIED, trigger="check_in", actor=actor, reason=f"نقل من {old_room.number}"
    )
    _retire_tasks(stay, f"نقل إلى {new_room.number}")
    reservation.room = new_room
    reservation.room_type = new_room.room_type
    reservation.total += difference
    reservation.rate_snapshot.setdefault("room_changes", []).append(
        {
            "date": today().isoformat(),
            "from": old_room.number,
            "to": new_room.number,
            "difference": difference,
            "reason": reason.strip(),
            "approved_by": str(approver.pk) if approver else None,
        }
    )
    reservation.save()
    if difference:
        billing.post_line(
            actor,
            billing.folio_of(reservation),
            kind="adjustment",
            description=f"فرق تغيير الغرفة {old_room.number} ← {new_room.number}",
            amount=difference,
            reason=reason,
        )
    audit.record(
        actor=actor,
        action="stay.change_room",
        entity="stay",
        entity_id=stay.pk,
        before=before,
        after={**snapshot(reservation), "approved_by": str(approver.pk) if approver else None},
    )
    return stay


# --- Checkout and cancellation ---------------------------------------------------------


def _close(stay: Stay, actor, *, status: str, room_status: str, maintenance_reason: str, why: str) -> None:
    reservation = stay.reservation
    _retire_tasks(stay, why)
    segment = _open_segment(stay)
    segment.to_date = max(today(), segment.from_date)
    segment.save()
    _leave_room(reservation.room, room_status, maintenance_reason, actor, why)
    reservation.status = status
    reservation.save()
    stay.checked_out_at = timezone.now()


@transaction.atomic
def checkout(
    actor,
    stay_id,
    *,
    room_status: str = "cleaning",
    maintenance_reason: str = "",
    override_password: str = "",
    override_reason: str = "",
    version: int | None = None,
) -> Stay:
    """Record departure; the room needs cleaning (or maintenance).

    With a balance ≠ 0 the manager must override with password and reason (spec §6.4, artboard 6.5 C);
    what is left stays on the closed folio as a debt (or credit) for the debt report.
    """
    stay = _stay_for_update(stay_id, version)
    before = snapshot(stay.reservation)
    folio = Folio.objects.select_for_update().get(reservation=stay.reservation)
    balance = billing.FolioTotals.of(folio).balance
    if balance != 0:
        if not override_password:
            raise ApiError("balance_not_zero", 409, balance=balance)
        stay.override_by = verify_manager_override(override_password, override_reason)
        stay.override_reason = override_reason.strip()
    _close(
        stay,
        actor,
        status=ReservationStatus.CHECKED_OUT,
        room_status=room_status,
        maintenance_reason=maintenance_reason,
        why=f"مغادرة {stay.reservation.guest.full_name}",
    )
    billing.close_folio(stay.reservation)
    stay.save()
    audit.record(
        actor=actor,
        action="stay.checkout",
        entity="stay",
        entity_id=stay.pk,
        before=before,
        after={
            **snapshot(stay.reservation),
            "balance_at_checkout": balance,
            "override_by": str(stay.override_by_id) if stay.override_by_id else None,
        },
    )
    return stay


def cancel_options(stay: Stay) -> tuple[int, list]:
    """Ways to settle the nights already used, priced at the booking's prices (V2 artboard 6.5 F)."""
    reservation = stay.reservation
    used = rules.consumed_nights(reservation.check_in_date, today())
    prices = reservation.rate_snapshot.get("prices") or prices_of(reservation.room_type)
    options = sorted(rules.options_for("daily", used), key=lambda o: rules.price(o, prices))
    return used, [(o, rules.price(o, prices)) for o in options]


@transaction.atomic
def cancel_stay(
    actor,
    stay_id,
    *,
    reason: str,
    option_key: str | None = None,
    manual_total: int | None = None,
    override_password: str,
    override_reason: str = "",
    refund_method: str = "cash",
    version: int | None = None,
) -> Stay:
    """End a stay early as «ملغاة»: nothing is deleted; the new total covers the nights used.

    The room charges are settled to ``new_total`` with an adjustment line (discounts included), and
    any excess already paid is refunded from the open shift (V2 artboard 6.5 F «يُرَدّ للنزيل»).
    """
    if not reason.strip():
        raise ApiError("reason_required", 400, detail="سبب الإلغاء مطلوب.")
    stay = _stay_for_update(stay_id, version)
    approver = verify_manager_override(override_password, override_reason or reason)
    used, options = cancel_options(stay)
    by_key = {o.key: total for o, total in options}
    if manual_total is not None:
        new_total, settlement = manual_total, "manual"
    elif option_key in by_key:
        new_total, settlement = by_key[option_key], option_key
    else:
        raise ApiError("pricing_choice_required", 400, options=list(by_key))

    reservation = stay.reservation
    before = snapshot(reservation)
    folio = Folio.objects.select_for_update().get(reservation=reservation)
    totals = billing.FolioTotals.of(folio)
    services_total = sum(folio.lines.filter(kind="service").values_list("amount", flat=True))
    settlement_line = new_total - (totals.total - services_total)
    if settlement_line:
        billing.post_line(
            actor,
            folio,
            kind="adjustment",
            description=f"تسوية إلغاء الإقامة — {used} ليلة مستهلكة",
            amount=settlement_line,
            reason=reason,
        )
    refund = billing_rules.refund_due(new_total + services_total, totals.paid)
    if refund:
        billing.take_payment(
            actor, folio, amount=-refund, method=refund_method, kind="refund", reason="ردّ عند إلغاء الإقامة"
        )
    reservation.rate_snapshot["cancellation"] = {
        "nights_used": used,
        "settlement": settlement,
        "previous_total": totals.total,
        "new_total": new_total,
        "refund": refund,
    }
    reservation.total = new_total
    reservation.status_reason = reason.strip()
    stay.override_by, stay.override_reason = approver, (override_reason or reason).strip()
    _close(
        stay,
        actor,
        status=ReservationStatus.CANCELLED,
        room_status="cleaning",
        maintenance_reason="",
        why=f"إلغاء إقامة {reservation.guest.full_name}",
    )
    billing.close_folio(reservation)
    stay.save()
    audit.record(
        actor=actor,
        action="stay.cancel",
        entity="stay",
        entity_id=stay.pk,
        before=before,
        after={**snapshot(reservation), "approved_by": str(approver.pk)},
    )
    return stay
