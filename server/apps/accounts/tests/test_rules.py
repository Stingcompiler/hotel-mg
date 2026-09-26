from datetime import UTC, datetime, timedelta

import pytest

from apps.accounts import rules

NOW = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)


def test_failures_before_the_fifth_only_count():
    assert rules.register_failure(0, NOW) == (1, None)
    assert rules.register_failure(3, NOW) == (4, None)


def test_fifth_failure_locks_for_five_minutes_and_resets_counter():
    assert rules.register_failure(4, NOW) == (0, NOW + timedelta(minutes=5))


def test_is_locked():
    assert not rules.is_locked(None, NOW)
    assert rules.is_locked(NOW + timedelta(seconds=1), NOW)
    assert not rules.is_locked(NOW, NOW)


def test_attempts_left():
    assert rules.attempts_left(0) == 5
    assert rules.attempts_left(2) == 3


@pytest.mark.parametrize(
    ("actor", "target", "allowed"),
    [
        ("owner", "owner", True),
        ("owner", "manager", True),
        ("manager", "manager", True),
        ("manager", "reception", True),
        ("manager", "owner", False),
        ("reception", "reception", False),
    ],
)
def test_can_manage_user(actor, target, allowed):
    assert rules.can_manage_user(actor, target) is allowed


def test_is_manager():
    assert rules.is_manager("manager") and rules.is_manager("owner")
    assert not rules.is_manager("reception")


def test_token_expiry_is_twelve_hours():
    assert not rules.token_expired(NOW, NOW + timedelta(hours=11, minutes=59))
    assert rules.token_expired(NOW, NOW + timedelta(hours=12))
