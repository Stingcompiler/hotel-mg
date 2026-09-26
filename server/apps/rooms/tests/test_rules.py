from datetime import date

import pytest

from apps.rooms import rules

TODAY = date(2026, 9, 26)


@pytest.mark.parametrize(
    ("frm", "to", "trigger"),
    [
        ("ready", "occupied", "check_in"),
        ("occupied", "cleaning", "checkout"),
        ("cleaning", "ready", "manual"),
        ("ready", "maintenance", "manual"),
        ("maintenance", "ready", "manual"),
        ("cleaning", "maintenance", "manual"),
        ("maintenance", "cleaning", "manual"),
    ],
)
def test_allowed_transitions(frm, to, trigger):
    assert rules.can_transition(frm, to, trigger)


@pytest.mark.parametrize(
    ("frm", "to", "trigger"),
    [
        ("occupied", "maintenance", "manual"),  # never from occupied
        ("occupied", "ready", "manual"),
        ("ready", "occupied", "manual"),  # only check-in occupies a room
        ("occupied", "cleaning", "manual"),  # only checkout frees it
        ("maintenance", "occupied", "check_in"),
        ("cleaning", "occupied", "check_in"),
        ("ready", "ready", "manual"),
    ],
)
def test_refused_transitions(frm, to, trigger):
    assert not rules.can_transition(frm, to, trigger)


def test_manual_targets():
    assert rules.manual_targets("ready") == ["maintenance"]
    assert rules.manual_targets("cleaning") == ["maintenance", "ready"]
    assert rules.manual_targets("maintenance") == ["cleaning", "ready"]
    assert rules.manual_targets("occupied") == []


def test_reason_required_for_maintenance_only():
    assert rules.reason_required("maintenance")
    assert not rules.reason_required("ready")


def test_overdue_is_derived_from_exclusive_checkout_date():
    # Stay 24 → 26 Sep (check_out_date exclusive): overdue from the 26th while still occupied.
    assert rules.is_overdue("occupied", TODAY, date(2026, 9, 26))
    assert not rules.is_overdue("occupied", TODAY, date(2026, 9, 27))
    assert not rules.is_overdue("cleaning", TODAY, date(2026, 9, 20))
    assert not rules.is_overdue("occupied", TODAY, None)


def test_out_of_service_and_bookable():
    assert not rules.can_take_out_of_service("occupied")
    assert rules.can_take_out_of_service("maintenance")
    assert rules.is_bookable("ready", True)
    assert not rules.is_bookable("ready", False)
    assert not rules.is_bookable("cleaning", True)
