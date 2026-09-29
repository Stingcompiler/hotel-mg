from apps.cash import rules


def test_expected_cash_matches_artboard():
    # 6.7 A: 50,000 + 190,000 cash − 12,500 cash expenses = 227,500 (bankak 120,000 and transfer 10,000 excluded)
    assert rules.expected_cash(5_000_000, 19_000_000, 1_250_000) == 22_750_000


def test_difference_and_reason():
    assert rules.difference(22_500_000, 22_750_000) == -250_000
    assert rules.difference_reason_required(22_500_000, 22_750_000)
    assert not rules.difference_reason_required(5_000_000, 5_000_000)


def test_attachment_missing():
    assert rules.attachment_missing(2_500_000, 2_000_000, False)
    assert not rules.attachment_missing(2_500_000, 2_000_000, True)
    assert not rules.attachment_missing(2_000_000, 2_000_000, False)  # «فوق 20,000»


def test_totals_by_method():
    assert rules.totals_by_method([("cash", 5), ("bankak", 7), ("cash", -2)]) == {
        "cash": 3,
        "bankak": 7,
        "transfer": 0,
        "total": 10,
    }


def test_the_cash_chain_rules():
    """Review 2026-09-29, A-6/A-7: what a shift leaves, what may be handed over, per-currency differences."""
    assert rules.left_in_drawer(3_500_000, 1_000_000) == 2_500_000
    assert rules.left_foreign({"USD": 20_000, "EUR": 500}, {"USD": 5_000, "EUR": 500}) == {"USD": 15_000}
    assert rules.handover_valid(100, 100, {"USD": 50}, {"USD": 50})
    assert not rules.handover_valid(100, 101, {}, {})
    assert not rules.handover_valid(100, -1, {}, {})
    assert not rules.handover_valid(100, 0, {"USD": 50}, {"USD": 60})
    assert not rules.handover_valid(100, 0, {}, {"EUR": 1})
    assert rules.foreign_differences({"USD": 100, "EUR": 5}, {"USD": 90, "EUR": 5, "SAR": 3}) == {"SAR": 3, "USD": -10}
    assert not rules.opening_differs(7, None, {"USD": 1}, {})  # the first shift: nothing to compare with
    assert not rules.opening_differs(7, 7, {"USD": 1}, {"USD": 1})
    assert rules.opening_differs(6, 7, {}, {})
    assert rules.opening_differs(7, 7, {}, {"USD": 1})
