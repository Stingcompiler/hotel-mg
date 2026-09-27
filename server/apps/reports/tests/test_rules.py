from datetime import date, datetime
from decimal import Decimal

import pytest

from apps.reports import rules


@pytest.mark.parametrize(
    ("n", "words"),
    [
        (0, "صفر"),
        (1, "واحد"),
        (11, "أحد عشر"),
        (21, "واحد وعشرون"),
        (100, "مائة"),
        (250, "مائتان وخمسون"),
        (1_000, "ألف"),
        (2_000, "ألفان"),
        (3_000, "ثلاثة آلاف"),
        (15_000, "خمسة عشر ألفًا"),
        (285_000, "مائتان وخمسة وثمانون ألفًا"),
        (1_250_500, "مليون ومائتان وخمسون ألفًا وخمسمائة"),
        (2_000_000_000, "ملياران"),
        (-5, "سالب خمسة"),
    ],
)
def test_number_to_words(n, words):
    assert rules.number_to_words(n) == words


def test_amount_in_words():
    assert rules.amount_in_words(1_500_000) == "خمسة عشر ألف جنيه"  # receipt 7.2 «بالحروف»
    assert rules.amount_in_words(150) == "واحد جنيه وخمسون قرشًا"
    assert rules.amount_in_words(-10_000) == "سالب مائة جنيه"


def test_to_major():
    assert rules.to_major(1_500_050, 0) == Decimal("15001")
    assert rules.to_major(1_500_049, 0) == Decimal("15000")
    assert rules.to_major(1_500_050, 2) == Decimal("15000.50")


def test_shift_label_and_helpers():
    assert rules.shift_label(datetime(2026, 9, 26, 8, 0)) == "صباحية"
    assert rules.shift_label(datetime(2026, 9, 26, 16, 0)) == "مسائية"
    assert rules.percent(18, 30) == 60 and rules.percent(1, 0) == 0
    assert rules.days_between(date(2026, 9, 1), date(2026, 9, 26)) == 25
    assert rules.occupancy_percent(17, 30, 1) == 59


@pytest.mark.parametrize(
    ("kind", "today", "period"),
    [
        ("month", date(2026, 9, 27), (date(2026, 9, 1), date(2026, 9, 27))),
        ("previous", date(2026, 9, 27), (date(2026, 8, 1), date(2026, 8, 31))),
        ("previous", date(2026, 1, 5), (date(2025, 12, 1), date(2025, 12, 31))),
        ("90days", date(2026, 9, 27), (date(2026, 6, 30), date(2026, 9, 27))),
    ],
)
def test_dashboard_period(kind, today, period):
    assert rules.dashboard_period(kind, today) == period


@pytest.mark.parametrize(
    ("kind", "start", "end", "compared"),
    [
        # Month to date: the same days of the previous month, not the whole of it.
        ("month", date(2026, 9, 1), date(2026, 9, 5), (date(2026, 8, 1), date(2026, 8, 5))),
        # Clamped to a shorter previous month.
        ("month", date(2026, 3, 1), date(2026, 3, 31), (date(2026, 2, 1), date(2026, 2, 28))),
        ("previous", date(2026, 8, 1), date(2026, 8, 31), (date(2026, 7, 1), date(2026, 7, 31))),
        ("90days", date(2026, 6, 30), date(2026, 9, 27), (date(2026, 4, 1), date(2026, 6, 29))),
    ],
)
def test_comparison_period_has_the_same_length(kind, start, end, compared):
    assert rules.comparison_period(kind, start, end) == compared


def test_week_label():
    assert rules.week_label(2, date(2026, 9, 8), date(2026, 9, 14), True) == "الأسبوع 2 (8–14)"
    assert rules.week_label(1, date(2026, 6, 30), date(2026, 7, 6), False) == "30/6–6/7"


def test_pounds_text():
    assert rules.pounds_text(150_000_000) == "1,500,000"
    assert rules.pounds_text(-150) == "−1"
    assert rules.pounds_text(-50) == "0"
    assert rules.pounds_text(0) == "0"
