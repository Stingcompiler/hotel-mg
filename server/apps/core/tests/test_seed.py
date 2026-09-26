import pytest
from django.core.management import CommandError, call_command

from apps.accounts.models import User
from apps.core.seed import demo_data

pytestmark = pytest.mark.django_db


def test_seed_loads_users_idempotently():
    call_command("seed_demo", "--allow-non-debug")
    call_command("seed_demo", "--allow-non-debug")
    assert User.objects.count() == len(demo_data.USERS)
    manager = User.objects.get(username="manager")
    assert manager.full_name == "المدير"
    assert manager.role == "manager" and manager.is_staff
    assert manager.check_pin(demo_data.DEMO_PIN)
    assert not User.objects.get(username="khalid.m").is_active


def test_seed_refuses_without_debug():
    with pytest.raises(CommandError):
        call_command("seed_demo")
    assert User.objects.count() == 0


def test_demo_rooms_match_design():
    assert len(demo_data.ROOMS) == 30
    assert {r["floor"] for r in demo_data.ROOMS} == {1, 2, 3, 4}
    types = {t["name"] for t in demo_data.ROOM_TYPES}
    assert {r["type"] for r in demo_data.ROOMS} == types
    assert all(isinstance(t[k], int) for t in demo_data.ROOM_TYPES for k in ("nightly", "weekly", "monthly"))
