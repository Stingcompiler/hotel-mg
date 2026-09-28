import pytest

from apps.billing import rules


def test_balance():
    assert rules.balance([30_000_000, -1_500_000], [10_000_000, 12_000_000]) == 6_500_000


@pytest.mark.parametrize(("method", "required"), [("cash", False), ("bankak", True), ("transfer", True)])
def test_reference_required(method, required):
    assert rules.reference_required(method) is required


def test_discount_limit():
    assert rules.discount_within_limit(6_000_000, 30_000_000, 20)
    assert not rules.discount_within_limit(6_000_100, 30_000_000, 20)


def test_refund_due():
    assert rules.refund_due(18_000_000, 27_000_000) == 9_000_000  # V2 cancel modal: 90,000
    assert rules.refund_due(18_000_000, 10_000_000) == 0


def test_payment_kind():
    assert rules.payment_kind(False, 100) == "deposit"
    assert rules.payment_kind(True, 100) == "payment"
    assert rules.payment_kind(True, -100) == "refund"


def test_running_ledger_and_columns():
    assert rules.as_debit_credit(500) == (500, 0)
    assert rules.as_debit_credit(-500) == (0, 500)
    rows = rules.running_ledger([{"debit": 300, "credit": 0}, {"debit": 0, "credit": 15}, {"debit": 50, "credit": 0}])
    assert [r["balance"] for r in rows] == [300, 285, 335]


@pytest.mark.parametrize(
    ("kind", "manager", "approved", "needs"),
    [
        ("room", False, False, True),
        ("discount", False, False, True),
        ("adjustment", False, False, True),
        ("room", True, False, False),
        ("room", False, True, False),
        ("service", False, False, False),
    ],
)
def test_line_reversal_needs_manager(kind, manager, approved, needs):
    assert rules.line_reversal_needs_manager(kind, manager, approved) is needs


@pytest.mark.parametrize(
    ("own", "manager", "approved", "needs"),
    [
        (True, False, False, False),
        (False, False, False, True),
        (False, True, False, False),
        (False, False, True, False),
    ],
)
def test_payment_reversal_needs_manager(own, manager, approved, needs):
    assert rules.payment_reversal_needs_manager(own, manager, approved) is needs
