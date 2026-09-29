"""Cash drawer arithmetic (spec §6.4, §6.5). Pure functions, no ORM. Amounts in minor units."""

CASH = "cash"


def expected_cash(opening: int, cash_receipts: int, cash_expenses: int) -> int:
    """النقدي المتوقع = الافتتاحي + المقبوضات النقدية − المصروفات النقدية. Bankak/transfers never enter the drawer."""
    return opening + cash_receipts - cash_expenses


def difference(counted: int, expected: int) -> int:
    """الفرق = المعدود − المتوقع: negative when the drawer is short."""
    return counted - expected


def difference_reason_required(counted: int, expected: int) -> bool:
    return difference(counted, expected) != 0


def attachment_missing(amount: int, threshold: int, has_attachment: bool) -> bool:
    """Expenses above the hotel's threshold need a receipt; flagged, not blocked («بانتظار مرفق»)."""
    return amount > threshold and not has_attachment


def totals_by_method(rows) -> dict[str, int]:
    """Sum (method, amount) pairs into {cash, bankak, transfer, total}."""
    totals = {"cash": 0, "bankak": 0, "transfer": 0}
    for method, amount in rows:
        totals[method] += amount
    totals["total"] = totals["cash"] + totals["bankak"] + totals["transfer"]
    return totals


def expense_reversal_needs_manager(own_expense_this_shift: bool, actor_is_manager: bool, approved: bool) -> bool:
    """Like payments (SEC-1): staff may undo their own expense in their open shift; anyone else's, or one from a closed
    shift, needs a manager (review 2026-09-29, A-14)."""
    return not own_expense_this_shift and not actor_is_manager and not approved


def reference_required(method: str) -> bool:
    """Bankak and transfers carry the transaction number, for expenses as for payments (A-15)."""
    return method != "cash"
