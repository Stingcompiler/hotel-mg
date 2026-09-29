"""Folios, lines and payments (spec §6.4). Every function runs inside the caller's or its own transaction."""

from collections import defaultdict
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Q, QuerySet, Sum
from django.utils import timezone

from apps.accounts import rules as account_rules
from apps.audit import services as audit
from apps.cash.services import require_open_shift
from apps.core.concurrency import get_for_update
from apps.core.errors import ApiError
from apps.core.hotel import current_hotel_id
from apps.core.models import HotelSettings

from . import rules
from .models import Currency, Folio, FolioLine, Payment, Sequence

LINE_FIELDS = ["folio", "kind", "description", "amount", "reverses", "reason", "posted_at"]
PAYMENT_FIELDS = [
    "folio",
    "shift",
    "kind",
    "method",
    "amount",
    "reference",
    "receipt_no",
    "reverses",
    "reason",
    "currency",
    "foreign_amount",
    "rate",
]
CURRENCY_FIELDS = ["code", "name", "symbol", "rate", "is_active"]


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
        return totals_by_folio(Folio.objects.filter(pk=folio.pk)).get(folio.pk) or cls.make(0, 0, 0)

    @classmethod
    def make(cls, total: int, discounts: int, paid: int) -> "FolioTotals":
        return cls(total - discounts, discounts, total, paid, rules.balance([total], [paid]))


def totals_by_folio(folios: QuerySet | None = None) -> dict:
    """folio id → FolioTotals in two grouped queries, for every folio or those of ``folios`` (a subquery, never an id
    list). The debts report, the owner dashboard and the report badges used two queries per folio: 80 s on five
    years of data (review 2026-09-29, F-1…F-3).

    A reversal counts with the kind it reverses: a cancelled discount is no longer shown as a discount on the invoice
    and the stay screen (review 2026-09-28, BIZ-7)."""
    lines, payments = FolioLine.objects.all(), Payment.objects.all()
    if folios is not None:
        lines, payments = lines.filter(folio__in=folios.values("pk")), payments.filter(folio__in=folios.values("pk"))
    sums = defaultdict(lambda: [0, 0, 0])  # total, discounts, paid
    for folio_id, kind, reversed_kind, s in (
        lines.order_by().values_list("folio_id", "kind", "reverses__kind").annotate(s=Sum("amount"))
    ):
        sums[folio_id][0] += s
        if "discount" in (kind, reversed_kind):
            sums[folio_id][1] += s
    for folio_id, s in payments.order_by().values_list("folio_id").annotate(s=Sum("amount")):
        sums[folio_id][2] += s
    return {folio_id: FolioTotals.make(*row) for folio_id, row in sums.items()}


def balances_by_folio(folios: QuerySet | None = None) -> dict:
    """folio id → balance (charges − payments) for every folio with a line or a payment, or those of ``folios`` (a
    subquery): two grouped queries on the folio column only, no joins (review 2026-09-29, F-1…F-3, F-7)."""
    lines, payments = FolioLine.objects.all(), Payment.objects.all()
    if folios is not None:
        lines, payments = (
            lines.filter(folio_id__in=folios.values("pk")),
            payments.filter(folio_id__in=folios.values("pk")),
        )
    charged = dict(lines.order_by().values_list("folio_id").annotate(s=Sum("amount")))
    paid = dict(payments.order_by().values_list("folio_id").annotate(s=Sum("amount")))
    return {pk: rules.balance([charged.get(pk, 0)], [paid.get(pk, 0)]) for pk in charged.keys() | paid.keys()}


def balances_by_reservation(reservations) -> dict:
    """Balance per reservation in two grouped queries. ``reservations``: a short id list (the board, one page) or a
    Reservation queryset, matched as a subquery — a long id list passes SQLite's limit of query variables
    (review 2026-09-29, F-7)."""
    if isinstance(reservations, QuerySet):
        folios = Folio.objects.filter(reservation__in=reservations.values("pk"))
        by_folio = balances_by_folio(folios)
        balance_of = {rid: by_folio.get(fid, 0) for fid, rid in folios.values_list("pk", "reservation_id")}
        return {rid: balance_of.get(rid, 0) for rid in reservations.values_list("pk", flat=True)}
    ids, match = reservations, {"folio__reservation_id__in": reservations}
    charged = dict(
        FolioLine.objects.filter(**match).order_by().values_list("folio__reservation_id").annotate(s=Sum("amount"))
    )
    paid = dict(
        Payment.objects.filter(**match).order_by().values_list("folio__reservation_id").annotate(s=Sum("amount"))
    )
    return {rid: rules.balance([charged.get(rid, 0)], [paid.get(rid, 0)]) for rid in ids}


def deposits_by_reservation(reservation_ids) -> dict:
    """Deposits paid per reservation in one grouped query (lists)."""
    return dict(
        Payment.objects.filter(kind="deposit", folio__reservation_id__in=reservation_ids)
        .order_by()
        .values_list("folio__reservation_id")
        .annotate(s=Sum("amount"))
    )


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


def stay_base(reservation) -> int:
    """The stay at list price: the booking, every extension and every room-change difference (rate snapshot)."""
    rate = reservation.rate_snapshot or {}
    base = rate.get("base_total") or 0
    base += sum(e.get("base_total") or 0 for e in rate.get("extensions", []))
    base += sum(c.get("difference") or 0 for c in rate.get("room_changes", []))
    return base


def check_discount(folio: Folio, discount: int, *, approver=None) -> None:
    """Discounts need a manager beyond the hotel's limit, counted over everything already taken off the stay, and
    always on a closed folio (a discount there only makes credit to pay out — review 2026-09-29, A-2, A-4)."""
    if approver is not None:
        return
    if folio.status == Folio.Status.CLOSED:
        raise ApiError("override_required", 403, detail="الخصم على فاتورة مغلقة يحتاج موافقة المدير.")
    services = Q(kind="service") | Q(kind="reversal", reverses__kind="service")
    net = folio.lines.exclude(services).aggregate(s=Sum("amount"))["s"] or 0
    limit = HotelSettings.load().max_discount_percent
    if rules.discount_needs_manager(stay_base(folio.reservation), net, discount, limit):
        raise ApiError("override_required", 403, detail=f"الخصم أكبر من {limit}٪ من قيمة الإقامة ويحتاج موافقة المدير.")


@transaction.atomic
def add_line(actor, folio_id, *, kind: str, description: str, amount: int, reason: str = "", approver=None):
    """Staff-entered service charge or discount (spec: discounts need a reason)."""
    folio = Folio.objects.select_for_update().select_related("reservation").get(pk=folio_id)
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
def reverse_line(actor, line_id, *, reason: str, approver=None) -> FolioLine:
    if not reason.strip():
        raise ApiError("reason_required", 400, detail="سبب العكس مطلوب.")
    line = FolioLine.objects.select_for_update().select_related("folio").get(pk=line_id)
    if line.kind == "reversal" or FolioLine.objects.filter(reverses=line).exists():
        raise ApiError("already_reversed", 409)
    if rules.line_reversal_needs_manager(line.kind, account_rules.is_manager(actor.role), approver is not None):
        raise ApiError("override_required", 403, detail="عكس بند الإقامة أو الخصم يحتاج موافقة المدير.")
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
    after = audit.snapshot(reversal, LINE_FIELDS)
    if approver:
        after["approved_by"] = str(approver.pk)
    audit.record(actor=actor, action="folio.reverse_line", entity="folio", entity_id=line.folio_id, after=after)
    return reversal


# --- Payments -------------------------------------------------------------------------------


def _checked_in_or_later(folio: Folio) -> bool:
    return folio.reservation.status in ("checked_in", "checked_out", "cancelled")


def in_currency(currency: str, foreign_amount: int | None) -> tuple[int, int]:
    """(base amount, rate) of an amount handed over in an accepted foreign currency, at the owner's current rate."""
    row = Currency.objects.filter(code=currency, is_active=True).first()
    if row is None:
        raise ApiError("validation_error", 400, detail="هذه العملة غير مقبولة — يضيفها المالك من الإعدادات › العملات.")
    if not foreign_amount or foreign_amount <= 0:
        raise ApiError("validation_error", 400, detail="المبلغ يجب أن يكون أكبر من صفر.")
    return rules.to_base(foreign_amount, row.rate), row.rate


def take_payment(
    actor,
    folio: Folio,
    *,
    amount: int,
    method: str,
    reference: str = "",
    kind: str | None = None,
    reason: str = "",
    currency: str = "",
    foreign_amount: int | None = None,
    rate: int | None = None,
) -> Payment:
    """Record money in (or out when negative) in this device's open shift. Caller owns the transaction.

    ``currency`` / ``foreign_amount`` / ``rate``: paid in a foreign currency; ``amount`` is then its base equivalent.
    """
    if rules.reference_required(method) and not reference.strip():
        raise ApiError("reference_required", 400)
    shift = require_open_shift()
    payment = Payment.objects.create(
        currency=currency,
        foreign_amount=foreign_amount if currency else None,
        rate=rate if currency else None,
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
def record_payment(
    actor,
    folio_id,
    *,
    method: str,
    amount: int | None = None,
    reference: str = "",
    currency: str = "",
    foreign_amount: int | None = None,
) -> Payment:
    rate = None
    if currency:
        amount, rate = in_currency(currency, foreign_amount)
    if not amount or amount <= 0:
        raise ApiError("validation_error", 400, detail="المبلغ يجب أن يكون أكبر من صفر.")
    folio = Folio.objects.select_for_update().select_related("reservation").get(pk=folio_id)
    return take_payment(
        actor,
        folio,
        amount=amount,
        method=method,
        reference=reference,
        currency=currency,
        foreign_amount=foreign_amount,
        rate=rate,
    )


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
def reverse_payment(actor, payment_id, *, reason: str, approver=None) -> Payment:
    """Undo a mistaken payment with an opposite row in the current shift (artboard 6.5: «عكس دفعة»)."""
    if not reason.strip():
        raise ApiError("reason_required", 400, detail="سبب العكس مطلوب.")
    original = Payment.objects.select_for_update().select_related("folio").get(pk=payment_id)
    if original.kind == "reversal" or Payment.objects.filter(reverses=original).exists():
        raise ApiError("already_reversed", 409)
    shift = require_open_shift()
    own = original.created_by_id == actor.pk and original.shift_id == shift.pk
    if rules.payment_reversal_needs_manager(own, account_rules.is_manager(actor.role), approver is not None):
        raise ApiError("override_required", 403, detail="عكس دفعة استلمها غيرك أو من وردية سابقة يحتاج موافقة المدير.")
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
        currency=original.currency,
        foreign_amount=-original.foreign_amount if original.foreign_amount is not None else None,
        rate=original.rate,
        created_by=actor,
    )
    after = audit.snapshot(reversal, PAYMENT_FIELDS)
    if approver:
        after["approved_by"] = str(approver.pk)
    audit.record(actor=actor, action="payment.reverse", entity="folio", entity_id=original.folio_id, after=after)
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
        if p.currency:
            text = f"{text} ({p.foreign_text()})"
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


# --- Currencies (owner decision 2026-09-28) --------------------------------------------------------


@transaction.atomic
def create_currency(actor, *, code: str, name: str, symbol: str = "", rate: int) -> Currency:
    code = code.strip().upper()
    if not rules.valid_currency_code(code, HotelSettings.load().currency):
        raise ApiError("validation_error", 400, detail="رمز العملة ثلاثة أحرف لاتينية (مثل USD) غير عملة الفندق.")
    if Currency.objects.filter(code=code).exists():
        raise ApiError("validation_error", 400, detail=f"العملة {code} موجودة — عدّل سعرها بدل إضافتها مرة أخرى.")
    if rate <= 0:
        raise ApiError("validation_error", 400, detail="السعر يجب أن يكون أكبر من صفر.")
    row = Currency.objects.create(code=code, name=name.strip(), symbol=symbol.strip(), rate=rate, created_by=actor)
    audit.record(
        actor=actor,
        action="currency.create",
        entity="currency",
        entity_id=row.pk,
        after=audit.snapshot(row, CURRENCY_FIELDS),
    )
    return row


@transaction.atomic
def update_currency(actor, currency_id, *, version: int, **changes) -> Currency:
    row = get_for_update(Currency.objects, currency_id, version)
    if "rate" in changes and changes["rate"] <= 0:
        raise ApiError("validation_error", 400, detail="السعر يجب أن يكون أكبر من صفر.")
    before = audit.snapshot(row, CURRENCY_FIELDS)
    for field, value in changes.items():
        setattr(row, field, value.strip() if isinstance(value, str) else value)
    row.save()
    audit.record(
        actor=actor,
        action="currency.update",
        entity="currency",
        entity_id=row.pk,
        before=before,
        after=audit.snapshot(row, CURRENCY_FIELDS),
    )
    return row
