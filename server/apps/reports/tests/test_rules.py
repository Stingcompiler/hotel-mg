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
