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


MANAGER_REVERSAL_KINDS = frozenset({"room", "discount", "adjustment"})


def line_reversal_needs_manager(kind: str, actor_is_manager: bool, approved: bool) -> bool:
    """Reversing a room charge, a discount or a room-change difference is a price decision: reception needs a
    manager (review 2026-09-28, SEC-1). A mistaken service line may be reversed by the person at the desk."""
    return kind in MANAGER_REVERSAL_KINDS and not actor_is_manager and not approved


def payment_reversal_needs_manager(own_payment_this_shift: bool, actor_is_manager: bool, approved: bool) -> bool:
    """Staff may undo their own payment in their open shift (e.g. entered twice); anyone else's money, or money
    from a closed shift, needs a manager."""
    return not own_payment_this_shift and not actor_is_manager and not approved


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


# --- Foreign currencies (owner decision 2026-09-28) -------------------------------------------------


def to_base(foreign_minor: int, rate: int) -> int:
    """Cents of a foreign currency → base minor units at ``rate`` (base minor per whole unit), rounded half away
    from zero: 150.00 $ at 2,500 → 37,500,000 minor (375,000 ج.س)."""
    numerator = foreign_minor * rate
    sign = -1 if numerator < 0 else 1
    whole, rest = divmod(abs(numerator), 100)
    return sign * (whole + (1 if 2 * rest >= 100 else 0))


def foreign_text(foreign_minor: int, symbol: str) -> str:
    """«150 $», «150.50 $», «-20 $»."""
    whole, cents = divmod(abs(foreign_minor), 100)
    number = f"{whole:,}" + (f".{cents:02d}" if cents else "")
    return f"{'-' if foreign_minor < 0 else ''}{number} {symbol}"


def rate_text(rate: int) -> str:
    """Base minor units per unit → «2,500» (or «2,500.50»)."""
    whole, minor = divmod(rate, 100)
    return f"{whole:,}" + (f".{minor:02d}" if minor else "")


def valid_currency_code(code: str, base: str) -> bool:
    """Three Latin capitals (ISO 4217) other than the hotel's own currency."""
    return len(code) == 3 and code.isascii() and code.isalpha() and code.isupper() and code != base


def foreign_totals(rows) -> dict[str, dict[str, int]]:
    """``rows``: (currency, method, foreign_amount, amount) of foreign-currency payments → per currency the cash in its
    own cents (what is in the drawer), all methods in its cents, and the base equivalent."""
    out: dict[str, dict[str, int]] = {}
    for currency, method, foreign_amount, amount in rows:
        row = out.setdefault(currency, {"cash": 0, "total": 0, "base": 0})
        row["total"] += foreign_amount
        row["base"] += amount
        if method == "cash":
            row["cash"] += foreign_amount
    return out
