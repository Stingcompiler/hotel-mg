"""Folios, lines and payments (spec §6.4). Every function runs inside the caller's or its own transaction."""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.audit import services as audit
from apps.cash.services import require_open_shift
from apps.core.errors import ApiError
from apps.core.hotel import current_hotel_id
from apps.core.models import HotelSettings

from . import rules
from .models import Folio, FolioLine, Payment, Sequence

LINE_FIELDS = ["folio", "kind", "description", "amount", "reverses", "reason", "posted_at"]
PAYMENT_FIELDS = ["folio", "shift", "kind", "method", "amount", "reference", "receipt_no", "reverses", "reason"]


def next_number(name: str) -> int:
    """Gap-free: the counter row is locked and bumped in the caller's transaction."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("next_number() must run inside a transaction")
    seq, _ = Sequence.objects.select_for_update().get_or_create(hotel_id=current_hotel_id(), name=name)
    seq.last += 1
    seq.save(update_fields=["last"])
    return seq.last


def open_folio(reservation, actor) -> Folio:
    return Folio.objects.create(reservation=reservation, invoice_no=next_number("invoice"), created_by=actor)


def folio_of(reservation) -> Folio:
    return Folio.objects.get(reservation=reservation)


def close_folio(reservation) -> Folio:
    """No new room charges after departure or cancellation; payments (debts, refunds) are still allowed."""
    folio = folio_of(reservation)
    folio.status = Folio.Status.CLOSED
    folio.save(update_fields=["status"])
    return folio


# --- Totals ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class FolioTotals:
    charges: int  # room + service + adjustments + reversals of lines (net of discounts below)
    discounts: int  # negative or 0
    total: int  # what the guest owes in all
    paid: int  # net of refunds and reversals
    balance: int  # total − paid; > 0 debt, < 0 credit

    @classmethod
    def of(cls, folio: Folio) -> "FolioTotals":
        lines = dict(folio.lines.values_list("kind").annotate(s=Sum("amount")))
        total = sum(lines.values())
        discounts = lines.get("discount", 0)
        paid = folio.payments.aggregate(s=Sum("amount"))["s"] or 0
        return cls(total - discounts, discounts, total, paid, rules.balance([total], [paid]))


def balances_by_reservation(reservation_ids) -> dict:
    """Balance per reservation in two queries (room board, lists)."""
    charged = dict(
        FolioLine.objects.filter(folio__reservation_id__in=reservation_ids)
        .values_list("folio__reservation_id")
        .annotate(s=Sum("amount"))
    )
    paid = dict(
        Payment.objects.filter(folio__reservation_id__in=reservation_ids)
        .values_list("folio__reservation_id")
        .annotate(s=Sum("amount"))
    )
    return {rid: rules.balance([charged.get(rid, 0)], [paid.get(rid, 0)]) for rid in reservation_ids}


# --- Lines ----------------------------------------------------------------------------------


def post_line(
    actor, folio: Folio, *, kind: str, description: str, amount: int, reason: str = "", approved_by=None
) -> FolioLine:
    """Append a line and audit it (with the approving manager, if any). Caller owns the transaction."""
    line = FolioLine.objects.create(
        folio=folio,
        kind=kind,
        description=description,
        amount=amount,
        reason=reason.strip(),
        posted_at=timezone.now(),
        created_by=actor,
    )
    after = audit.snapshot(line, LINE_FIELDS)
    if approved_by:
        after["approved_by"] = str(approved_by)
    audit.record(actor=actor, action=f"folio.{kind}", entity="folio", entity_id=folio.pk, after=after)
    return line


def check_discount(folio: Folio, discount: int, *, approver=None) -> None:
    """Discounts above the hotel's limit need a manager (password override or a manager at the desk)."""
    room_charges = folio.lines.filter(kind="room").aggregate(s=Sum("amount"))["s"] or 0
    already = -(folio.lines.filter(kind="discount").aggregate(s=Sum("amount"))["s"] or 0)
    limit = HotelSettings.load().max_discount_percent
    if approver is None and not rules.discount_within_limit(already + discount, room_charges, limit):
        raise ApiError("override_required", 403, detail=f"الخصم أكبر من {limit}٪ من قيمة الإقامة ويحتاج موافقة المدير.")


@transaction.atomic
def add_line(actor, folio_id, *, kind: str, description: str, amount: int, reason: str = "", approver=None):
    """Staff-entered service charge or discount (spec: discounts need a reason)."""
    folio = Folio.objects.select_for_update().get(pk=folio_id)
    if kind == "discount":
        if not reason.strip():
            raise ApiError("reason_required", 400, detail="سبب الخصم مطلوب عند إدخال أي خصم.")
        check_discount(folio, amount, approver=approver)
        return post_line(
            actor,
            folio,
            kind="discount",
            description=description or f"خصم: {reason}",
            amount=-amount,
            reason=reason,
            approved_by=approver.pk if approver else None,
        )
    return post_line(actor, folio, kind=kind, description=description, amount=amount, reason=reason)


@transaction.atomic
def reverse_line(actor, line_id, *, reason: str) -> FolioLine:
    if not reason.strip():
        raise ApiError("reason_required", 400, detail="سبب العكس مطلوب.")
    line = FolioLine.objects.select_for_update().select_related("folio").get(pk=line_id)
    if line.kind == "reversal" or FolioLine.objects.filter(reverses=line).exists():
        raise ApiError("already_reversed", 409)
    reversal = FolioLine.objects.create(
        folio=line.folio,
        kind="reversal",
        description=f"عكس: {line.description}",
        amount=-line.amount,
        reverses=line,
        reason=reason.strip(),
        posted_at=timezone.now(),
        created_by=actor,
    )
    audit.record(
        actor=actor,
        action="folio.reverse_line",
        entity="folio",
        entity_id=line.folio_id,
        after=audit.snapshot(reversal, LINE_FIELDS),
    )
    return reversal


# --- Payments -------------------------------------------------------------------------------


def _checked_in_or_later(folio: Folio) -> bool:
    return folio.reservation.status in ("checked_in", "checked_out", "cancelled")


def take_payment(
    actor, folio: Folio, *, amount: int, method: str, reference: str = "", kind: str | None = None, reason: str = ""
) -> Payment:
    """Record money in (or out when negative) in this device's open shift. Caller owns the transaction."""
    if rules.reference_required(method) and not reference.strip():
        raise ApiError("reference_required", 400)
    shift = require_open_shift()
    payment = Payment.objects.create(
        folio=folio,
        shift=shift,
        kind=kind or rules.payment_kind(_checked_in_or_later(folio), amount),
        method=method,
        amount=amount,
        reference=reference.strip(),
        receipt_no=next_number("receipt"),
        reason=reason.strip(),
        received_at=timezone.now(),
        created_by=actor,
    )
    audit.record(
        actor=actor,
        action=f"payment.{payment.kind}",
        entity="folio",
        entity_id=folio.pk,
        after=audit.snapshot(payment, PAYMENT_FIELDS),
    )
    return payment


@transaction.atomic
def record_payment(actor, folio_id, *, amount: int, method: str, reference: str = "") -> Payment:
    if amount <= 0:
        raise ApiError("validation_error", 400, detail="المبلغ يجب أن يكون أكبر من صفر.")
    folio = Folio.objects.select_for_update().select_related("reservation").get(pk=folio_id)
    return take_payment(actor, folio, amount=amount, method=method, reference=reference)


@transaction.atomic
def refund(actor, folio_id, *, amount: int, method: str, reason: str, reference: str = "") -> Payment:
    """Give money back (e.g. unused nights). Needs a reason and cannot exceed what the guest is owed."""
    if not reason.strip():
        raise ApiError("reason_required", 400, detail="سبب الردّ مطلوب.")
    folio = Folio.objects.select_for_update().select_related("reservation").get(pk=folio_id)
    if amount <= 0 or amount > -FolioTotals.of(folio).balance:
        raise ApiError("refund_exceeds_credit", 400)
    return take_payment(actor, folio, amount=-amount, method=method, reference=reference, kind="refund", reason=reason)


@transaction.atomic
def reverse_payment(actor, payment_id, *, reason: str) -> Payment:
    """Undo a mistaken payment with an opposite row in the current shift (artboard 6.5: «عكس دفعة»)."""
    if not reason.strip():
        raise ApiError("reason_required", 400, detail="سبب العكس مطلوب.")
    original = Payment.objects.select_for_update().select_related("folio").get(pk=payment_id)
    if original.kind == "reversal" or Payment.objects.filter(reverses=original).exists():
        raise ApiError("already_reversed", 409)
    shift = require_open_shift()
    reversal = Payment.objects.create(
        folio=original.folio,
        shift=shift,
        kind="reversal",
        method=original.method,
        amount=-original.amount,
        reference=original.reference,
        receipt_no=next_number("receipt"),
        reverses=original,
        reason=reason.strip(),
        received_at=timezone.now(),
        created_by=actor,
    )
    audit.record(
        actor=actor,
        action="payment.reverse",
        entity="folio",
        entity_id=original.folio_id,
        after=audit.snapshot(reversal, PAYMENT_FIELDS),
    )
    return reversal


# --- Ledger ---------------------------------------------------------------------------------


def ledger(folio: Folio) -> list[dict]:
    """Lines and payments in time order with a running balance (artboard 6.5 «دفتر الفاتورة»)."""
    entries = []
    for line in folio.lines.select_related("created_by", "reverses"):
        debit, credit = rules.as_debit_credit(line.amount)
        entries.append(
            {
                "at": line.posted_at,
                "type": "line",
                "id": line.pk,
                "kind": line.kind,
                "text": line.description,
                "debit": debit,
                "credit": credit,
                "reference": "",
                "reason": line.reason,
                "reverses": line.reverses_id,
                "by": line.created_by.full_name if line.created_by else "",
            }
        )
    for p in folio.payments.select_related("created_by"):
        debit, credit = rules.as_debit_credit(-p.amount)
        text = f"{p.get_kind_display()} — {p.get_method_display()}"
        entries.append(
            {
                "at": p.received_at,
                "type": "payment",
                "id": p.pk,
                "kind": p.kind,
                "text": f"{text}: {p.reason}" if p.reason else text,
                "debit": debit,
                "credit": credit,
                "reference": p.reference,
                "reason": p.reason,
                "reverses": p.reverses_id,
                "by": p.created_by.full_name if p.created_by else "",
            }
        )
    entries.sort(key=lambda e: e["at"])
    return rules.running_ledger(entries)
