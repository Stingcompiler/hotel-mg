"""Stay use cases: check-in, extend, change room, checkout, cancel (spec §6.1-§6.4).

Each posts its folio lines (room charge, extension, room-change difference, cancellation settlement).
Follow-up task supersession arrives with the alert engine in B3.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
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
from .services import (
    approve_price,
    available_rooms,
    check_type_capacity,
    create_reservation,
    lock_room_for,
    prices_of,
    quote,
    snapshot,
    today,
)


def _stay_for_update(stay_id, version: int | None) -> Stay:
    stay = get_for_update(Stay.objects.select_related("reservation"), stay_id, version)
    if stay.reservation.status != ReservationStatus.CHECKED_IN:
        raise ApiError("invalid_reservation_status", 409)
    return stay


def _retire_tasks(stay: Stay, reason: str, actor=None, action: str = "") -> None:
    """Pending follow-up tasks of the stay become superseded; the engine re-plans from the new end (spec §6.6).

    ``action`` (extend / confirm_checkout) is recorded on the alerts already due: the staff answered them here.
    """
    from apps.followups.services import supersede_for_stay  # followups depends on stays; import at use

    supersede_for_stay(stay, actor, reason, action)


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
            approved_by=discount.get("approved_by"),
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
    override_password: str = "",
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
    approver = approve_price(option.total, final_total, override_password, override_reason)
    lock_room_for(reservation.room, reservation.check_out_date, q.check_out_date, exclude_pk=reservation.pk)
    check_type_capacity(reservation.room_type, reservation.check_out_date, q.check_out_date, exclude_pk=reservation.pk)

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
            "approved_by": str(approver.pk) if approver else None,
        }
    )
    reservation.save()
    segment = _open_segment(stay)
    segment.to_date = q.check_out_date
    segment.save()
    _retire_tasks(stay, f"تمديد حتى {rules.last_night(q.check_out_date):%d/%m}", actor, "extend")
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
    # The whole stay (booking + every extension) priced at the CURRENT type against the new one: a second change
    # starts from where the first left the guest, and extended nights count (review 2026-09-28, BIZ-1/2).
    rate = reservation.rate_snapshot
    units = rate.get("units") or {}
    parts = [rules.Option(units.get("monthly", 0), units.get("weekly", 0), units.get("daily", 0))]
    parts += [rules.parse_option_key(e.get("option", "")) or rules.Option(0, 0, 0) for e in rate.get("extensions", [])]
    option = rules.combine(*parts)
    if option.nights == 0:  # snapshot without units (e.g. migrated data): price by nights
        option = rules.Option(0, 0, reservation.nights)
    old_total = rules.price(option, prices_of(reservation.room_type))
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
    if reservation.check_out_date <= today() and room.room_type_id != reservation.room_type_id:
        # No booked night is left to price the difference on: the move would be free (review 2026-09-29, A-17).
        raise ApiError("stay_overdue", 409)
    end = max(reservation.check_out_date, today() + timedelta(days=1))
    new_room = lock_room_for(room, today(), end, exclude_pk=reservation.pk)
    if new_room.room_type_id != reservation.room_type_id:
        check_type_capacity(new_room.room_type, today(), end, exclude_pk=reservation.pk)
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
            "until": end.isoformat(),  # the nights the difference was priced for (early departure, A-5)
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
    _retire_tasks(stay, why, actor, "confirm_checkout")
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
    refund_method: str = "cash",
    refund_reference: str = "",
    version: int | None = None,
) -> Stay:
    """Record departure; the room needs cleaning (or maintenance).

    Leaving before the booked departure settles the room charges to the nights used at the prices paid and refunds
    the rest from the open shift (owner decision 4, review 2026-09-29). With a balance ≠ 0 after that the manager
    must override with password and reason (spec §6.4, artboard 6.5 C); what is left stays on the closed folio as a
    debt (or credit) for the debt report.
    """
    stay = _stay_for_update(stay_id, version)
    before = snapshot(stay.reservation)
    folio = Folio.objects.select_for_update().get(reservation=stay.reservation)
    early = _settle_early_departure(actor, stay, folio, refund_method, refund_reference)
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
            "early_departure": early,
            "override_by": str(stay.override_by_id) if stay.override_by_id else None,
        },
    )
    return stay


def _settle_early_departure(actor, stay: Stay, folio: Folio, refund_method: str, refund_reference: str) -> dict | None:
    quote = early_departure(stay)
    if quote is None:
        return None
    reservation = stay.reservation
    if settle := quote["new_room_charges"] - quote["room_charges"]:
        billing.post_line(
            actor,
            folio,
            kind="adjustment",
            description=f"مغادرة مبكرة — {rules.count_label('daily', quote['nights_used'])} من "
            f"{rules.count_label('daily', quote['nights_booked'])} بالسعر المدفوع",
            amount=settle,
            reason="مغادرة مبكرة",
        )
    if quote["refund"]:
        billing.take_payment(
            actor,
            folio,
            amount=-quote["refund"],
            method=refund_method,
            reference=refund_reference,
            kind="refund",
            reason="ردّ الليالي غير المستهلكة عند المغادرة المبكرة",
        )
    reservation.rate_snapshot["early_departure"] = {k: quote[k] for k in ("nights_used", "nights_booked", "refund")}
    reservation.rate_snapshot["early_departure"]["previous_total"] = quote["room_charges"]
    reservation.total = reservation.total + settle
    return quote


def services_total(folio) -> int:
    """Services on the folio net of their reversals: they stay charged when a stay is cancelled (BIZ-5)."""
    return sum(
        folio.lines.filter(Q(kind="service") | Q(kind="reversal", reverses__kind="service")).values_list(
            "amount", flat=True
        )
    )


@dataclass(frozen=True)
class UsedNights:
    """The nights used so far, priced at what was paid (owner decision 4, review 2026-09-29 A-5)."""

    used: int  # nights used (at least one)
    early: bool  # the booking runs past them
    room_charges: int  # room charges on the folio now: booking, extensions, changes, discounts, adjustments
    services: int  # services net of reversals: charged in full
    paid: int
    charge: int  # room charges for the nights used, at the prices paid


def used_nights(stay: Stay, folio: Folio) -> UsedNights:
    reservation = stay.reservation
    used = rules.consumed_nights(reservation.check_in_date, today())
    totals = billing.FolioTotals.of(folio)
    services = services_total(folio)
    room_charges = totals.total - services
    blocks = rules.charge_blocks(
        reservation.check_in_date, reservation.check_out_date, reservation.total, reservation.rate_snapshot
    )
    until = reservation.check_in_date + timedelta(days=used)
    charge = rules.used_room_charge(blocks, until, room_charges)
    return UsedNights(used, until < reservation.check_out_date, room_charges, services, totals.paid, charge)


def cancel_options(stay: Stay) -> tuple[int, list[dict]]:
    """Ways to settle the nights already used (V2 artboard 6.5 F): first at the prices paid, then the list prices of
    the booking — never above the stay's room charges now (review 2026-09-29, A-5)."""
    reservation = stay.reservation
    u = used_nights(stay, billing.folio_of(reservation))
    prices = reservation.rate_snapshot.get("prices") or prices_of(reservation.room_type)
    options = sorted(rules.options_for("daily", u.used), key=lambda o: rules.price(o, prices))
    return u.used, [
        {"key": "paid", "label": f"بالسعر المدفوع — {rules.count_label('daily', u.used)}", "total": u.charge},
        *(
            {"key": o.key, "label": rules.option_label(o), "total": min(rules.price(o, prices), u.room_charges)}
            for o in options
        ),
    ]


def early_departure(stay: Stay) -> dict | None:
    """Leaving before the booked departure: the nights used at the prices paid and the rest refunded (owner decision 4,
    review 2026-09-29). None when the guest leaves on the booked day or later."""
    u = used_nights(stay, billing.folio_of(stay.reservation))
    if not u.early:
        return None
    refund = billing_rules.refund_due(u.charge + u.services, u.paid)
    return {
        "nights_used": u.used,
        "nights_booked": stay.reservation.nights,
        "room_charges": u.room_charges,
        "new_room_charges": u.charge,
        "services": u.services,
        "paid": u.paid,
        "refund": refund,
        "balance_after": u.charge + u.services - u.paid + refund,
    }


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
    refund_reference: str = "",
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
    by_key = {o["key"]: o["total"] for o in options}
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
    # Services net of their reversals: a reversed laundry line is not charged again (review 2026-09-28, BIZ-5).
    services = services_total(folio)
    settlement_line = new_total - (totals.total - services)
    if settlement_line:
        billing.post_line(
            actor,
            folio,
            kind="adjustment",
            description=f"تسوية إلغاء الإقامة — {used} ليلة مستهلكة",
            amount=settlement_line,
            reason=reason,
        )
    refund = billing_rules.refund_due(new_total + services, totals.paid)
    if refund:
        billing.take_payment(
            actor,
            folio,
            amount=-refund,
            method=refund_method,
            reference=refund_reference,
            kind="refund",
            reason="ردّ عند إلغاء الإقامة",
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
