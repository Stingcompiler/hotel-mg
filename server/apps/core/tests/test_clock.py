from datetime import UTC, datetime, timedelta

import pytest

from apps.core import rules
from apps.core.clock import approve_clock, is_clock_blocked, observe_clock
from apps.core.models import SystemClock

T0 = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (timedelta(0), False),
        (timedelta(hours=1), False),
        (-timedelta(minutes=5), False),  # within tolerance
        (-timedelta(minutes=5, seconds=1), True),
        (-timedelta(days=1), True),
    ],
)
def test_is_clock_rollback(offset, expected):
    assert rules.is_clock_rollback(T0 + offset, T0) is expected


def test_is_clock_rollback_without_history():
    assert rules.is_clock_rollback(T0, None) is False


@pytest.mark.django_db
class TestObserveClock:
    def test_first_observation_records_time(self):
        assert observe_clock(T0) is False
        assert SystemClock.load().last_seen_at == T0

    def test_moves_forward_never_backward(self):
        observe_clock(T0)
        observe_clock(T0 + timedelta(hours=2))
        observe_clock(T0 + timedelta(hours=2) - timedelta(minutes=3))  # small drift is tolerated
        assert SystemClock.load().last_seen_at == T0 + timedelta(hours=2)
        assert not is_clock_blocked()

    def test_rollback_blocks_until_approved(self):
        observe_clock(T0)
        assert observe_clock(T0 - timedelta(hours=1)) is True
        assert is_clock_blocked()
        assert SystemClock.load().blocked_at == T0 - timedelta(hours=1)
        # Moving the clock forward again does not lift the block.
        assert observe_clock(T0 + timedelta(hours=1)) is True

        approve_clock(now=T0 - timedelta(hours=1))
        assert not is_clock_blocked()
        assert observe_clock(T0 - timedelta(minutes=30)) is False
