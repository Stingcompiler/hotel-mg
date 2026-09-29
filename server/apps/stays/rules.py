"""Stay dates, durations, pricing decompositions and overlap (spec §6.1, §6.2). Pure functions, no ORM.

Dates are hotel-local calendar dates. ``check_out_date`` is exclusive: a stay of N nights starting on D
has check_out_date = D + N and ends at the end of D + N - 1.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction

NIGHTS_PER_UNIT = {"daily": 1, "weekly": 7, "monthly": 30}
UNIT_ORDER = ("monthly", "weekly", "daily")
MAX_NIGHTS = 366
BLOCKING_STATUSES = frozenset({"confirmed", "checked_in"})

# (one, two, 3-10, 11+) — Arabic number agreement.
UNIT_LABELS = {
    "monthly": ("شهر", "شهران", "أشهر", "شهرًا"),
    "weekly": ("أسبوع", "أسبوعان", "أسابيع", "أسبوعًا"),
    "daily": ("ليلة", "ليلتان", "ليالٍ", "ليلة"),
}


@dataclass(frozen=True)
class Option:
    """One way to price a number of nights, e.g. 1 week + 3 nights."""

    monthly: int
    weekly: int
    daily: int

    @property
    def key(self) -> str:
        return f"m{self.monthly}w{self.weekly}d{self.daily}"

    @property
    def nights(self) -> int:
        return self.monthly * 30 + self.weekly * 7 + self.daily

    def units(self) -> dict[str, int]:
        return {"monthly": self.monthly, "weekly": self.weekly, "daily": self.daily}


def nights_for(kind: str, count: int) -> int:
    if kind not in NIGHTS_PER_UNIT:
        raise ValueError(f"unknown duration kind {kind!r}")
    if count < 1:
        raise ValueError("count must be at least 1")
    return NIGHTS_PER_UNIT[kind] * count


def check_out_for(check_in: date, nights: int) -> date:
    return check_in + timedelta(days=nights)


def last_night(check_out: date) -> date:
    """The stay ends at the end of this day."""
    return check_out - timedelta(days=1)


def options_for(kind: str, count: int) -> list[Option]:
    """Pricing choices the staff pick from (spec §6.1).

    Weekly and monthly are exact. Daily stays of 7+ nights also offer the greedy mix of larger units
    (e.g. 10 nights → 1 week + 3 nights, or 10 nights) — the staff choose explicitly.
    """
    nights = nights_for(kind, count)
    if kind == "monthly":
        return [Option(count, 0, 0)]
    if kind == "weekly":
        return [Option(0, count, 0)]
    candidates = [
        Option(nights // 30, (nights % 30) // 7, (nights % 30) % 7),  # months, then weeks, then nights
        Option(0, nights // 7, nights % 7),  # weeks, then nights
        Option(0, 0, nights),  # nightly rate only
    ]
    seen, result = set(), []
    for option in candidates:
        if option.key not in seen:
            seen.add(option.key)
            result.append(option)
    return result


_OPTION_KEY = re.compile(r"m(\d+)w(\d+)d(\d+)")


def parse_option_key(key: str) -> Option | None:
    """«m1w0d3» → Option(1, 0, 3); None for anything else (older snapshots)."""
    match = _OPTION_KEY.fullmatch(key or "")
    return Option(*(int(g) for g in match.groups())) if match else None


def combine(*options: Option) -> Option:
    """The whole stay as one option: the booking plus every extension (for pricing a room change)."""
    return Option(sum(o.monthly for o in options), sum(o.weekly for o in options), sum(o.daily for o in options))


def price(option: Option, prices: dict[str, int]) -> int:
    """Total in minor units. ``prices`` has nightly/weekly/monthly in minor units."""
    return option.monthly * prices["monthly"] + option.weekly * prices["weekly"] + option.daily * prices["nightly"]


def duration_kind_of(option: Option) -> str:
    used = [unit for unit in UNIT_ORDER if option.units()[unit]]
    return used[0] if len(used) == 1 else "mixed"


def count_label(unit: str, n: int) -> str:
    """«ليلة», «ليلتان», «3 ليالٍ», «30 ليلة»."""
    one, two, few, many = UNIT_LABELS[unit]
    if n == 1:
        return one
    if n == 2:
        return two
    return f"{n} {few if n <= 10 else many}"


def option_label(option: Option) -> str:
    """Arabic label as on the New Reservation artboard: «أسبوع + 3 ليالٍ», «10 ليالٍ»."""
    parts = [count_label(unit, n) for unit, n in option.units().items() if n]
    return " + ".join(parts)


def option_formula(option: Option, prices: dict[str, int]) -> str:
    """Human formula in major units, e.g. «77,000 + 3 × 12,000»."""
    unit_price = {"monthly": prices["monthly"], "weekly": prices["weekly"], "daily": prices["nightly"]}
    parts = []
    for unit, n in option.units().items():
        if n:
            amount = f"{unit_price[unit] // 100:,}"
            parts.append(amount if n == 1 else f"{n} × {amount}")
    return " + ".join(parts)


def overlaps(a_in: date, a_out: date, b_in: date, b_out: date) -> bool:
    """Half-open date ranges [in, out) intersect (spec §6.2)."""
    return a_in < b_out and a_out > b_in


def blocking_until(status: str, check_out: date, today: date) -> date:
    """Until when an existing reservation blocks its room.

    A checked-in guest keeps the room until checkout is recorded, even past the end date (overdue):
    treat the room as held at least through today.
    """
    if status == "checked_in":
        return max(check_out, today + timedelta(days=1))
    return check_out


def peak_overlap(ranges: list[tuple[date, date]], check_in: date, check_out: date) -> int:
    """Most of ``ranges`` ([in, out)) that share one night of [check_in, check_out) — the type's busiest night."""
    peak, day = 0, check_in
    while day < check_out:
        peak = max(peak, sum(1 for a, b in ranges if a <= day < b))
        day += timedelta(days=1)
    return peak


def override_needs_reason(base_total: int, final_total: int) -> bool:
    return final_total != base_total


# --- Stays ---------------------------------------------------------------------------


def can_check_in(check_in: date, check_out: date, today: date) -> bool:
    """From the arrival day (or a late arrival) until the last night."""
    return check_in <= today < check_out


def remaining_nights(check_out: date, today: date) -> int:
    return max((check_out - today).days, 0)


def consumed_nights(check_in: date, today: date) -> int:
    """Nights used so far; a guest who checked in is charged at least one night."""
    return max((today - check_in).days, 1)


def round_div(numerator: int, denominator: int) -> int:
    """Integer division rounded half away from zero (money stays integral, no floats)."""
    sign = -1 if (numerator < 0) != (denominator < 0) else 1
    q, r = divmod(abs(numerator), abs(denominator))
    return sign * (q + (1 if 2 * r >= abs(denominator) else 0))


def room_change_difference(old_total: int, new_total: int, remaining: int, nights: int) -> int:
    """Price difference for moving to another room type for the remaining nights.

    Pro-rates the difference between the booking priced at the old and at the new type,
    rounded to whole pounds (100 minor units). Same type → 0.
    """
    if nights <= 0 or remaining <= 0:
        return 0
    return round_div((new_total - old_total) * remaining, nights * 100) * 100


def charge_blocks(check_in: date, check_out: date, total: int, snapshot: dict) -> list[tuple[date, date, int]]:
    """The stay's room charges as blocks of nights with the price agreed for each: the booking, every extension,
    every room change's difference (from its day to the departure). ``total`` is the reservation's room total."""
    extensions = snapshot.get("extensions", [])
    changes = snapshot.get("room_changes", [])
    booked_out = date.fromisoformat(extensions[0]["from"]) if extensions else check_out
    booking = total - sum(e["total"] for e in extensions) - sum(c["difference"] for c in changes)
    blocks = [(check_in, booked_out, booking)]
    blocks += [(date.fromisoformat(e["from"]), date.fromisoformat(e["to"]), e["total"]) for e in extensions]
    blocks += [
        (
            date.fromisoformat(c["date"]),
            date.fromisoformat(c["until"]) if c.get("until") else check_out,
            c["difference"],
        )
        for c in changes
    ]
    return blocks


def used_room_charge(blocks: list[tuple[date, date, int]], used_until: date, room_charges: int) -> int:
    """Room charges for the nights before ``used_until``, at the prices paid (owner decision 4, review 2026-09-29).

    Each block counts for the share of its nights that were used; the result is scaled to the folio's room charges
    now (discounts, agreed prices and adjustments included) so it never exceeds them (A-5)."""
    full = sum(amount for _, _, amount in blocks)
    if full <= 0 or room_charges <= 0:
        return 0
    used = Fraction(0)
    for start, end, amount in blocks:
        nights = (end - start).days
        if nights > 0:
            used += Fraction(amount * min(max((used_until - start).days, 0), nights), nights)
    share = used * room_charges / full
    return min(max(round_div(share.numerator, share.denominator), 0), room_charges)


def after_room_statuses(choice: str) -> list[str]:
    """Statuses the vacated room goes through: always cleaning first (spec §6.3), then maybe maintenance."""
    if choice not in ("cleaning", "maintenance"):
        raise ValueError(f"unknown room status after leaving: {choice!r}")
    return ["cleaning"] if choice == "cleaning" else ["cleaning", "maintenance"]


KIND_ADJECTIVE = {"daily": "يومية", "weekly": "أسبوعية", "monthly": "شهرية"}


def room_line_text(kind: str, room_type: str, room_number: str, nights: int, label: str = "") -> str:
    """Folio line for the room charge: «إقامة شهرية — مزدوجة 203 (30 ليلة)» (artboard 6.5 ledger)."""
    if kind in KIND_ADJECTIVE:
        return f"إقامة {KIND_ADJECTIVE[kind]} — {room_type} {room_number} ({count_label('daily', nights)})"
    return f"إقامة — {room_type} {room_number} ({label or count_label('daily', nights)})"
