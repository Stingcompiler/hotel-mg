"""Data for the print templates (spec §8, artboards 7.1–7.3). The SPA renders them; the server supplies facts."""

from django.utils import timezone

from apps.accounts import rules as account_rules
from apps.billing.models import Folio, Payment
from apps.billing.services import FolioTotals, ledger
from apps.cash.models import Expense, Shift
from apps.cash.services import ShiftTotals, movements
from apps.core.models import HotelSettings
from apps.guests import rules as guest_rules
from apps.stays import rules as stay_rules
from apps.stays.models import DurationKind, ReservationStatus

from . import rules


def hotel_header() -> dict:
    s = HotelSettings.load()
    return {
        "name_ar": s.name_ar,
        "name_latin": s.name_latin,
        "address": s.address,
        "phone": s.phone,
        "digits": s.digits,
        "money_decimals": s.money_decimals,
    }


def _stay_state(reservation) -> str:
    today = timezone.localdate()
    last = stay_rules.last_night(reservation.check_out_date)
    if reservation.status == ReservationStatus.CHECKED_IN:
        if reservation.check_out_date <= today:
            return f"متجاوزة — انتهت بنهاية يوم {last:%d/%m/%Y}"
        return f"جارية — تنتهي بنهاية يوم {last:%d/%m/%Y}"
    return ReservationStatus(reservation.status).label


def _invoice_items(folio: Folio, nights: int) -> list[dict]:
    """Artboard 7.1 line items (البيان · الكمية · السعر · الإجمالي): charges net of reversals; discounts go to the
    totals block. A single room line covers the whole stay, so its quantity is the nights; the rest count one."""
    lines = list(folio.lines.select_related("reverses"))
    reversed_ids = {line.reverses_id for line in lines if line.reverses_id}
    live = [line for line in lines if line.kind not in ("discount", "reversal") and line.pk not in reversed_ids]
    room_lines = [line for line in live if line.kind == "room"]
    items = []
    for line in live:
        quantity = nights if (line.kind == "room" and len(room_lines) == 1 and nights > 0) else 1
        items.append(
            {
                "at": line.posted_at,
                "kind": line.get_kind_display(),
                "text": line.description,
                "quantity": quantity,
                "unit_price": line.amount // quantity if quantity else line.amount,
                "total": line.amount,
            }
        )
    return items


def _invoice_payments(folio: Folio) -> list[dict]:
    """Every payment, refund and reversal in time order (the artboard's payment list)."""
    return [
        {
            "at": p.received_at,
            "receipt": p.receipt_label,
            "kind": p.get_kind_display(),
            "method": f"{p.get_method_display()} ({p.foreign_text()})" if p.currency else p.get_method_display(),
            "reference": p.reference,
            "amount": p.amount,
        }
        for p in folio.payments.all()
    ]


def invoice(folio: Folio, printed_by) -> dict:
    """Artboard 7.1: header, guest, room and stay, line items, totals with the discount, payment list, signatures.
    The running ledger stays in the document for the stay screen and older clients."""
    r = folio.reservation
    g = r.guest
    totals = FolioTotals.of(folio)
    manager = account_rules.is_manager(printed_by.role)
    return {
        "hotel": hotel_header(),
        "invoice": folio.invoice_label,
        "printed_at": timezone.now(),
        "printed_by": printed_by.full_name,
        "guest": {
            "name": g.full_name,
            "phone": g.phone,
            "id_type": g.get_id_type_display() if g.id_type else "",
            # Spec §5: the full number is for manager/owner only; reception prints the masked form.
            "id_number": g.id_number if manager else guest_rules.mask_id_number(g.id_number),
            "companions": [c.name for c in g.companions.filter(removed=False)],
        },
        "stay": {
            "room": r.room.number if r.room_id else None,
            "room_type": r.room_type.name,
            "duration_kind": DurationKind(r.duration_kind).label,
            "check_in_date": r.check_in_date,
            "last_night": stay_rules.last_night(r.check_out_date),
            "nights": r.nights,
            "state": _stay_state(r),
        },
        "ledger": ledger(folio),
        "items": _invoice_items(folio, r.nights),
        "payments": _invoice_payments(folio),
        "totals": {
            "charges": totals.charges,
            "discount": -totals.discounts,
            "total": totals.total,
            "paid": totals.paid,
            "balance": totals.balance,
        },
        "notes": [
            "الأسعار بالجنيه السوداني. القيود المسبوقة بـ «عكس» تُلغي قيدًا سابقًا ولا تُحذف.",
            "المتبقي مستحق عند تسجيل الخروج أو قبله. التمديد يُحسب بالسعر الساري وقت التمديد.",
            f"هذه الفاتورة مولَّدة من النظام؛ الرقم {folio.invoice_label} مرجعها في سجل التدقيق.",
        ],
    }


def payment_receipt(payment: Payment) -> dict:
    """Artboard 7.2 (80 mm): receipt number, amount in figures and words, stay totals after this payment."""
    folio = payment.folio
    r = folio.reservation
    totals = FolioTotals.of(folio)
    opened = timezone.localtime(payment.shift.opened_at)
    return {
        "hotel": hotel_header(),
        "receipt": payment.receipt_label,
        "kind": payment.get_kind_display(),
        "at": payment.received_at,
        "room": r.room.number if r.room_id else None,
        "guest": r.guest.full_name,
        "invoice": folio.invoice_label,
        # The stay period (design gap #11): the guest sees what the receipt is for.
        "check_in_date": r.check_in_date,
        "last_night": stay_rules.last_night(r.check_out_date),
        "nights": r.nights,
        "amount": payment.amount,
        "amount_in_words": rules.amount_in_words(payment.amount),
        "paid_in": payment.foreign_text() or None,
        "method": payment.get_method_display(),
        "reference": payment.reference,
        "stay_total": totals.total,
        "paid_to_date": totals.paid,
        "balance": totals.balance,
        "by": payment.created_by.full_name if payment.created_by else "",
        "shift": f"{opened:%d/%m} · {rules.shift_label(opened)}",
    }


def expense_receipt(expense: Expense) -> dict:
    """Artboard 7.2 expense slip: number, category, note, amount, method, recorder, signature line."""
    return {
        "hotel": hotel_header(),
        "number": expense.label,
        "at": expense.spent_at,
        "category": expense.get_category_display(),
        "note": expense.note if not expense.reverses_id else f"تصحيح: {expense.reason}",
        "room": expense.room.number if expense.room_id else None,
        "amount": expense.amount,
        "amount_in_words": rules.amount_in_words(expense.amount),
        "method": expense.get_method_display() + (" — من الدرج" if expense.method == "cash" else ""),
        "by": expense.created_by.full_name if expense.created_by else "",
    }


def shift_statement(shift: Shift, printed_by) -> dict:
    """Artboard 7.3: the approved model for printed reports (header, tiles, table, signatures)."""
    totals = ShiftTotals.of(shift)
    return {
        "hotel": hotel_header(),
        "shift": {
            "id": str(shift.pk),
            "device": shift.device,
            "opened_at": shift.opened_at,
            "closed_at": shift.closed_at,
            "opened_by": shift.created_by.full_name if shift.created_by else "",
            "closed_by": shift.closed_by.full_name if shift.closed_by else "",
        },
        "printed_at": timezone.now(),
        "printed_by": printed_by.full_name,
        "tiles": {
            "opening": shift.opening,
            "receipts": totals.receipts,
            "cash_expenses": totals.expenses["cash"],
            "expected": shift.expected if shift.expected is not None else totals.expected,
        },
        "movements": movements(shift),
        "counted": shift.counted,
        "difference": shift.difference,
        "difference_reason": shift.difference_reason,
        "handed_over": shift.handed_over,
        "left_in_drawer": shift.counted - shift.handed_over if shift.counted is not None else None,
        "opening_expected": shift.opening_expected,
        "opening_reason": shift.opening_reason,
        # The dollars and other currencies of the drawer, each in its own units (review 2026-09-29, A-9, D-1).
        "currencies": [
            {
                "currency": row["currency"],
                "symbol": row["symbol"],
                "opening": row["opening"],
                "received": row["cash"],
                "expected": row["expected"],
                "counted": shift.counted_foreign.get(row["currency"], 0) if shift.closed_at else None,
                "difference": shift.counted_foreign.get(row["currency"], 0) - row["expected"]
                if shift.closed_at
                else None,
                "handed_over": shift.handed_over_foreign.get(row["currency"], 0),
                "base": row["base"],
            }
            for row in totals.foreign
        ],
        "formula": rules.CASH_FORMULA,
    }
