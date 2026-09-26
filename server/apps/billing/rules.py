"""Folio arithmetic (spec §6.4). Pure functions, no ORM. Amounts are signed minor units."""

NON_CASH = frozenset({"bankak", "transfer"})


def balance(line_amounts, payment_amounts) -> int:
    """المتبقي = Σ lines − Σ payments. Reversals carry opposite signs, so no special cases."""
    return sum(line_amounts) - sum(payment_amounts)


def reference_required(method: str) -> bool:
    """«المرجع مطلوب لغير النقدي» (artboard 6.4 B)."""
    return method in NON_CASH


def discount_within_limit(discount: int, charges: int, max_percent: int) -> bool:
    """A discount up to max_percent of the room charges needs no manager (larger ones do, spec §6.8)."""
    return discount * 100 <= charges * max_percent


def refund_due(total_charges: int, paid: int) -> int:
    """What the guest gets back when charges fall below what was paid (V2 cancel modal «يُرَدّ للنزيل»)."""
    return max(paid - total_charges, 0)


def payment_kind(checked_in_or_later: bool, amount: int) -> str:
    """Money taken before arrival is a deposit («عربون»); negative amounts are refunds."""
    if amount < 0:
        return "refund"
    return "payment" if checked_in_or_later else "deposit"


def running_ledger(entries):
    """Add a running balance to chronological entries of (debit, credit) and return them.

    ``entries``: dicts with ``debit`` and ``credit`` (non-negative ints). Mutates and returns the list.
    """
    total = 0
    for entry in entries:
        total += entry["debit"] - entry["credit"]
        entry["balance"] = total
    return entries


def as_debit_credit(amount: int) -> tuple[int, int]:
    """A folio line (+ charge / − credit) or a negated payment as ledger columns."""
    return (amount, 0) if amount > 0 else (0, -amount)
