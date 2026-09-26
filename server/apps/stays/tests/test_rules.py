from datetime import date

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
