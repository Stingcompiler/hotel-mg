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
