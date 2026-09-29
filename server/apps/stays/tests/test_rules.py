from datetime import date, timedelta

import pytest

from apps.stays import rules
from apps.stays.rules import Option

SINGLE = {"nightly": 1_200_000, "weekly": 7_700_000, "monthly": 28_000_000}


@pytest.mark.parametrize(("kind", "count", "nights"), [("daily", 10, 10), ("weekly", 2, 14), ("monthly", 1, 30)])
def test_nights_for(kind, count, nights):
    assert rules.nights_for(kind, count) == nights


def test_nights_for_rejects_bad_input():
    with pytest.raises(ValueError):
        rules.nights_for("yearly", 1)
    with pytest.raises(ValueError):
        rules.nights_for("daily", 0)


def test_monthly_from_first_of_october_ends_end_of_30th():
    # Artboard 6.4 A: شهري ×1 from Thu 1 Oct → «تنتهي بنهاية يوم الجمعة 30 أكتوبر 2026 (30 ليلة)»
    check_out = rules.check_out_for(date(2026, 10, 1), 30)
    assert check_out == date(2026, 10, 31)
    assert rules.last_night(check_out) == date(2026, 10, 30)


def test_ten_daily_nights_offer_week_plus_three_or_ten_nights():
    # Artboard 6.4 B: 27 Sep, daily ×10 → «أسبوع + 3 ليالٍ» 113,000 or «10 ليالٍ» 120,000
    options = rules.options_for("daily", 10)
    assert [o.key for o in options] == ["m0w1d3", "m0w0d10"]
    assert [rules.price(o, SINGLE) for o in options] == [11_300_000, 12_000_000]
    assert [rules.option_label(o) for o in options] == ["أسبوع + 3 ليالٍ", "10 ليالٍ"]
    assert rules.option_formula(options[0], SINGLE) == "77,000 + 3 × 12,000"
    assert rules.option_formula(options[1], SINGLE) == "10 × 12,000"
    assert rules.check_out_for(date(2026, 9, 27), 10) == date(2026, 10, 7)


def test_short_daily_and_exact_kinds_have_one_option():
    assert rules.options_for("daily", 3) == [Option(0, 0, 3)]
    assert rules.options_for("weekly", 2) == [Option(0, 2, 0)]
    assert rules.options_for("monthly", 1) == [Option(1, 0, 0)]


def test_long_daily_stay_offers_month_mix():
    keys = [o.key for o in rules.options_for("daily", 40)]
    assert keys == ["m1w1d3", "m0w5d5", "m0w0d40"]


def test_duration_kind_of():
    assert rules.duration_kind_of(Option(0, 1, 3)) == "mixed"
    assert rules.duration_kind_of(Option(0, 0, 10)) == "daily"
    assert rules.duration_kind_of(Option(2, 0, 0)) == "monthly"
    assert Option(1, 1, 3).nights == 40


@pytest.mark.parametrize(
    ("unit", "n", "label"),
    [
        ("daily", 1, "ليلة"),
        ("daily", 2, "ليلتان"),
        ("daily", 3, "3 ليالٍ"),
        ("daily", 30, "30 ليلة"),
        ("weekly", 2, "أسبوعان"),
        ("weekly", 11, "11 أسبوعًا"),
        ("monthly", 4, "4 أشهر"),
    ],
)
def test_count_label(unit, n, label):
    assert rules.count_label(unit, n) == label


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ((1, 5), (5, 8), False),  # back-to-back: checkout day is the next arrival day
        ((1, 5), (4, 8), True),
        ((4, 8), (1, 5), True),
        ((1, 10), (3, 4), True),
        ((6, 8), (1, 5), False),
    ],
)
def test_overlaps_half_open(a, b, expected):
    d = lambda n: date(2026, 10, n)  # noqa: E731
    assert rules.overlaps(d(a[0]), d(a[1]), d(b[0]), d(b[1])) is expected


def test_blocking_until_keeps_overdue_room_held():
    today = date(2026, 9, 26)
    assert rules.blocking_until("checked_in", date(2026, 9, 24), today) == date(2026, 9, 27)
    assert rules.blocking_until("checked_in", date(2026, 10, 2), today) == date(2026, 10, 2)
    assert rules.blocking_until("confirmed", date(2026, 9, 24), today) == date(2026, 9, 24)


def test_override_needs_reason():
    assert rules.override_needs_reason(11_300_000, 10_500_000)
    assert not rules.override_needs_reason(11_300_000, 11_300_000)


# --- Stays ---


def test_can_check_in_from_arrival_until_last_night():
    arrive, leave = date(2026, 9, 26), date(2026, 9, 29)
    assert rules.can_check_in(arrive, leave, date(2026, 9, 26))
    assert rules.can_check_in(arrive, leave, date(2026, 9, 28))  # late arrival
    assert not rules.can_check_in(arrive, leave, date(2026, 9, 25))
    assert not rules.can_check_in(arrive, leave, date(2026, 9, 29))


def test_remaining_and_consumed_nights():
    assert rules.remaining_nights(date(2026, 10, 31), date(2026, 10, 13)) == 18
    assert rules.remaining_nights(date(2026, 9, 25), date(2026, 9, 26)) == 0
    assert rules.consumed_nights(date(2026, 10, 1), date(2026, 10, 13)) == 12  # V2 cancel modal: 12 nights
    assert rules.consumed_nights(date(2026, 9, 26), date(2026, 9, 26)) == 1


@pytest.mark.parametrize(("a", "b", "q"), [(7, 2, 4), (5, 2, 3), (-5, 2, -3), (-7, 2, -4), (4, 2, 2), (1, 3, 0)])
def test_round_div_half_away_from_zero(a, b, q):
    assert rules.round_div(a, b) == q


def test_room_change_difference():
    # Monthly double 300,000 → suite 520,000 with 22 of 30 nights left: 220,000 × 22/30 ≈ 161,333 → whole pounds
    assert rules.room_change_difference(30_000_000, 52_000_000, 22, 30) == 16_133_300
    assert rules.room_change_difference(30_000_000, 30_000_000, 22, 30) == 0
    assert rules.room_change_difference(52_000_000, 30_000_000, 22, 30) == -16_133_300
    assert rules.room_change_difference(30_000_000, 52_000_000, 0, 30) == 0
    assert rules.room_change_difference(30_000_000, 52_000_000, 5, 0) == 0


def test_after_room_statuses():
    assert rules.after_room_statuses("cleaning") == ["cleaning"]
    assert rules.after_room_statuses("maintenance") == ["cleaning", "maintenance"]
    with pytest.raises(ValueError):
        rules.after_room_statuses("ready")


def test_room_line_text():
    assert rules.room_line_text("monthly", "مزدوجة", "203", 30) == "إقامة شهرية — مزدوجة 203 (30 ليلة)"
    assert rules.room_line_text("daily", "مفردة", "101", 3) == "إقامة يومية — مفردة 101 (3 ليالٍ)"
    assert rules.room_line_text("mixed", "مفردة", "101", 10, "أسبوع + 3 ليالٍ") == "إقامة — مفردة 101 (أسبوع + 3 ليالٍ)"


def test_parse_option_key_and_combine():
    assert rules.parse_option_key("m1w0d3") == Option(1, 0, 3)
    assert rules.parse_option_key("") is None and rules.parse_option_key("weekly") is None
    assert rules.combine(Option(0, 0, 3), Option(0, 1, 2), Option(1, 0, 0)) == Option(1, 1, 5)


def test_peak_overlap():
    d = date(2026, 9, 26)
    ranges = [(d, date(2026, 9, 29)), (date(2026, 9, 28), date(2026, 9, 30)), (date(2026, 10, 1), date(2026, 10, 2))]
    assert rules.peak_overlap(ranges, d, date(2026, 10, 2)) == 2  # the 28th
    assert rules.peak_overlap(ranges, date(2026, 9, 29), date(2026, 10, 1)) == 1
    assert rules.peak_overlap([], d, date(2026, 9, 27)) == 0


def test_used_room_charge_prices_the_nights_used_at_what_was_paid():
    d = date(2026, 9, 1)
    # A month booked for 600 at an agreed price, 10 nights used: a third, never the list price.
    assert rules.used_room_charge([(d, d + timedelta(30), 60_000)], d + timedelta(10), 60_000) == 20_000
    # Upgrade from day 21 (difference 10 000 for the last 10 nights) and a 7-night extension for 14 000.
    snap = {
        "extensions": [{"from": "2026-10-01", "to": "2026-10-08", "total": 14_000}],
        "room_changes": [{"date": "2026-09-21", "until": "2026-10-01", "difference": 10_000}],
    }
    blocks = rules.charge_blocks(d, d + timedelta(37), 84_000, snap)
    assert blocks[0] == (d, d + timedelta(30), 60_000)
    assert rules.used_room_charge(blocks, d + timedelta(20), 84_000) == 40_000  # before the upgrade
    assert rules.used_room_charge(blocks, d + timedelta(37), 84_000) == 84_000  # everything, never more
    # A later discount of 8 400 (10 %) applies to the nights used as well.
    assert rules.used_room_charge(blocks, d + timedelta(20), 75_600) == 36_000
    assert rules.used_room_charge(blocks, d, 84_000) == 0
    assert rules.used_room_charge([(d, d, 5_000)], d + timedelta(3), 5_000) == 0  # an empty block
    assert rules.used_room_charge([(d, d + timedelta(3), 0)], d + timedelta(1), 0) == 0  # a free stay
    assert rules.charge_blocks(d, d + timedelta(3), 9_000, {}) == [(d, d + timedelta(3), 9_000)]
    older = {"room_changes": [{"date": "2026-09-03", "difference": 100}]}  # before 1.1.11: no «until»
    assert rules.charge_blocks(d, d + timedelta(5), 1_000, older)[1] == (d + timedelta(2), d + timedelta(5), 100)
