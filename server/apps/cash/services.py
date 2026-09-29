"""Cash shifts and expenses (spec §6.4, §6.5)."""

from dataclasses import dataclass

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.audit import services as audit
from apps.core import imaging
from apps.core.concurrency import get_for_update
from apps.core.errors import ApiError
from apps.core.models import HotelSettings

from . import rules
from .models import Expense, ExpenseAttachment, Shift

SHIFT_FIELDS = ["device", "opened_at", "opening", "closed_at", "closed_by", "expected", "counted", "difference_reason"]
EXPENSE_FIELDS = [
    "shift",
    "category",
    "amount",
    "note",
    "method",
    "reference",
    "room",
    "spent_at",
    "reverses",
    "reason",
]


def device() -> str:
    return settings.RUNTIME.device_name


def current_shift() -> Shift | None:
    return Shift.objects.filter(device=device(), closed_at__isnull=True).first()


def require_open_shift() -> Shift:
    """Every payment and expense belongs to the open shift of this device (409 ``no_open_shift``)."""
    shift = current_shift()
    if shift is None:
        raise ApiError("no_open_shift", 409)
    return shift


# --- Totals ------------------------------------------------------------------------------


def payment_rows(shift: Shift) -> list[tuple[str, int]]:
    """(method, amount) of base-currency payments recorded in the shift; refunds and reversals are negative.

    Foreign-currency payments are not in the pounds drawer: ``foreign_rows`` lists them per currency.
    """
    from apps.billing.models import Payment  # billing depends on cash, not the reverse

    return list(Payment.objects.filter(shift=shift, currency="").values_list("method", "amount"))


def foreign_rows(shift: Shift) -> list[tuple[str, str, int, int]]:
    from apps.billing.models import Payment

    return list(
        Payment.objects.filter(shift=shift)
        .exclude(currency="")
        .values_list("currency", "method", "foreign_amount", "amount")
    )


def foreign_summary(shift: Shift) -> list[dict]:
    """Per foreign currency received in the shift: cash in the drawer (its cents), all methods, base equivalent."""
    from apps.billing import rules as billing_rules
    from apps.billing.models import Currency

    totals = billing_rules.foreign_totals(foreign_rows(shift))
    symbols = dict(Currency.objects.filter(code__in=totals).values_list("code", "symbol"))
    return [{"currency": code, "symbol": symbols.get(code) or code, **row} for code, row in sorted(totals.items())]


@dataclass(frozen=True)
class ShiftTotals:
    opening: int
    receipts: dict  # {cash, bankak, transfer, total} in the base currency
    expenses: dict  # {cash, bankak, transfer, total}
    expected: int  # pounds in the drawer
    foreign: list  # [{currency, symbol, cash, total, base}] received in other currencies

    @classmethod
    def of(cls, shift: Shift) -> "ShiftTotals":
        receipts = rules.totals_by_method(payment_rows(shift))
        expenses = rules.totals_by_method(shift.expenses.values_list("method", "amount"))
        return cls(
            shift.opening,
            receipts,
            expenses,
            rules.expected_cash(shift.opening, receipts["cash"], expenses["cash"]),
            foreign_summary(shift),
        )


# --- Shifts ------------------------------------------------------------------------------


@transaction.atomic
def open_shift(actor, *, opening: int) -> Shift:
    if current_shift() is not None:
        raise ApiError("shift_already_open", 409)
    try:
        with transaction.atomic():
            shift = Shift.objects.create(device=device(), opened_at=timezone.now(), opening=opening, created_by=actor)
    except IntegrityError:  # a concurrent open on the same device won the race
        raise ApiError("shift_already_open", 409) from None
    audit.record(
        actor=actor, action="shift.open", entity="shift", entity_id=shift.pk, after=audit.snapshot(shift, SHIFT_FIELDS)
    )
    return shift


@transaction.atomic
def close_shift(actor, *, counted: int, difference_reason: str = "", version: int | None = None) -> Shift:
    shift = require_open_shift()
    shift = get_for_update(Shift.objects, shift.pk, version)
    expected = ShiftTotals.of(shift).expected
    reason = difference_reason.strip()
    if rules.difference_reason_required(counted, expected) and not reason:
        raise ApiError(
            "reason_required", 400, detail="سبب الفرق مطلوب.", difference=rules.difference(counted, expected)
        )
    before = audit.snapshot(shift, SHIFT_FIELDS)
    shift.closed_at = timezone.now()
    shift.closed_by = actor
    shift.expected = expected
    shift.counted = counted
    shift.difference_reason = reason
    shift.save()
    from apps.backup.services import after_shift_close  # backup depends on cash, not the reverse

    after_shift_close()
    audit.record(
        actor=actor,
        action="shift.close",
        entity="shift",
        entity_id=shift.pk,
        before=before,
        after=audit.snapshot(shift, SHIFT_FIELDS),
    )
    return shift


def movements(shift: Shift) -> list[dict]:
    """Everything that moved money in the shift, newest first (artboard 6.7 «حركات الوردية»)."""
    from apps.billing.models import Payment

    rows = [
        {
            "at": shift.opened_at,
            "kind": "open",
            "text": "رصيد افتتاحي",
            "amount": shift.opening,
            "method": "cash",
            "reference": "",
            "by": shift.created_by.full_name if shift.created_by else "",
            "ref_id": str(shift.pk),
        }
    ]
    for e in shift.expenses.select_related("created_by"):
        text = f"{e.note} — الفئة: {e.get_category_display()}"
        if e.reverses_id:
            text = f"تصحيح: {e.reason}"
        rows.append(
            {
                "at": e.spent_at,
                "kind": "out",
                "text": text,
                "amount": -e.amount,
                "method": e.method,
                "reference": e.reference,
                "by": e.created_by.full_name if e.created_by else "",
                "ref_id": str(e.pk),
            }
        )
    for p in Payment.objects.filter(shift=shift).select_related(
        "created_by", "folio__reservation__room", "folio__reservation__guest"
    ):
        rows.append(
            {
                "at": p.received_at,
                "kind": "in",
                "text": p.description(),
                "amount": p.amount,
                "method": p.method,
                "reference": p.reference,
                "by": p.created_by.full_name if p.created_by else "",
                "ref_id": str(p.pk),
            }
        )
    return sorted(rows, key=lambda r: r["at"], reverse=True)


def _next_expense_number() -> int:
    from apps.billing.services import next_number  # billing depends on cash, not the reverse

    return next_number("expense")


# --- Expenses ----------------------------------------------------------------------------


@transaction.atomic
def create_expense(actor, *, category, amount: int, note: str, method: str, reference="", room=None) -> Expense:
    if amount <= 0:
        raise ApiError("validation_error", 400, detail="المبلغ يجب أن يكون أكبر من صفر.")
    if rules.reference_required(method) and not reference.strip():
        raise ApiError("reference_required", 400)
    shift = require_open_shift()
    expense = Expense.objects.create(
        number=_next_expense_number(),
        shift=shift,
        category=category,
        amount=amount,
        note=note.strip(),
        method=method,
        reference=reference.strip(),
        room=room,
        spent_at=timezone.now(),
        created_by=actor,
    )
    audit.record(
        actor=actor,
        action="expense.create",
        entity="expense",
        entity_id=expense.pk,
        after=audit.snapshot(expense, EXPENSE_FIELDS),
    )
    return expense


@transaction.atomic
def reverse_expense(actor, expense_id, *, reason: str, approver=None) -> Expense:
    """Correct a mistaken expense with an opposite row in the current shift (never edit or delete)."""
    from apps.accounts import rules as account_rules

    if not reason.strip():
        raise ApiError("reason_required", 400, detail="سبب العكس مطلوب.")
    original = Expense.objects.select_for_update().get(pk=expense_id)
    if original.reverses_id or Expense.objects.filter(reverses=original).exists():
        raise ApiError("already_reversed", 409)
    shift = require_open_shift()
    own = original.created_by_id == actor.pk and original.shift_id == shift.pk
    if rules.expense_reversal_needs_manager(own, account_rules.is_manager(actor.role), approver is not None):
        raise ApiError("override_required", 403, detail="عكس مصروف سجّله غيرك أو من وردية سابقة يحتاج موافقة المدير.")
    reversal = Expense.objects.create(
        number=_next_expense_number(),
        shift=shift,
        category=original.category,
        amount=-original.amount,
        note=original.note,
        method=original.method,
        reference=original.reference,
        room=original.room,
        spent_at=timezone.now(),
        reverses=original,
        reason=reason.strip(),
        created_by=actor,
    )
    audit.record(
        actor=actor,
        action="expense.reverse",
        entity="expense",
        entity_id=original.pk,
        after=audit.snapshot(reversal, EXPENSE_FIELDS),
    )
    return reversal


@transaction.atomic
def add_expense_attachment(actor, expense_id, raw: bytes) -> ExpenseAttachment:
    expense = Expense.objects.get(pk=expense_id)
    try:
        stored = imaging.store_image(raw, f"expenses/{expense.pk}")
    except imaging.InvalidImage:
        raise ApiError("invalid_image", 400) from None
    try:
        attachment = ExpenseAttachment.objects.create(
            expense=expense, file_path=stored.relative_path, size=stored.size, sha256=stored.sha256, created_by=actor
        )
        audit.record(
            actor=actor,
            action="expense.attach",
            entity="expense",
            entity_id=expense.pk,
            after={"attachment": str(attachment.pk), "sha256": stored.sha256},
        )
    except Exception:
        stored.absolute_path.unlink(missing_ok=True)
        raise
    return attachment


def attachment_missing(expense: Expense, threshold: int | None = None) -> bool:
    threshold = HotelSettings.load().expense_attachment_threshold if threshold is None else threshold
    return rules.attachment_missing(expense.amount, threshold, expense.attachments.exists())


def expenses_total(qs) -> int:
    return qs.aggregate(total=Sum("amount"))["total"] or 0
