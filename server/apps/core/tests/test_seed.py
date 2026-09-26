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


def test_seed_loads_rooms_idempotently():
    from apps.rooms.models import Room, RoomType

    call_command("seed_demo", "--allow-non-debug")
    call_command("seed_demo", "--allow-non-debug")
    assert RoomType.objects.count() == 3
    assert Room.objects.count() == 30
    assert Room.objects.get(number="410").status == "maintenance"
    assert Room.objects.get(number="410").maintenance_reason.startswith("تسرب مياه")
    assert set(Room.objects.filter(status="cleaning").values_list("number", flat=True)) == {"104", "306"}
    assert RoomType.objects.get(name="مزدوجة").rooms.count() == 16


def test_seed_matches_room_board():
    from apps.stays.board import board

    call_command("seed_demo", "--allow-non-debug")
    call_command("seed_demo", "--allow-non-debug")
    data = board()
    rows = {r["number"]: r for r in data["rooms"]}
    assert data["summary"]["occupied"] == 18  # «مشغولة 18/30»
    assert data["summary"]["occupancy_percent"] == 60
    assert data["summary"]["overdue"] == 2  # 207 and 305
    assert data["summary"]["departures_today"] == 2  # 108 and 204 «تنتهي اليوم»
    assert rows["305"]["display_status"] == "overdue" and rows["305"]["stay"]["days_left"] == -2
    assert rows["203"]["stay"]["guest_name"] == "محمد عثمان الطيب" and rows["203"]["stay"]["days_left"] == 3
    assert rows["411"]["stay"]["days_left"] == 18
    assert rows["102"]["status"] == "ready" and rows["102"]["next_reservation"]["guest_name"] == "خالد إبراهيم عبدالله"
    assert rows["410"]["status"] == "maintenance"


def test_seed_money_matches_brief():
    from apps.cash.services import ShiftTotals, current_shift
    from apps.stays.board import board

    call_command("seed_demo", "--allow-non-debug")
    call_command("seed_demo", "--allow-non-debug")
    rows = {r["number"]: r for r in board()["rooms"]}
    assert rows["203"]["stay"]["balance"] == 1_500_000
    assert rows["305"]["stay"]["balance"] == 4_200_000
    assert rows["411"]["stay"]["balance"] == 0
    shift = current_shift()
    assert shift.opening == 5_000_000 and shift.created_by.username == "ahmed.ali"
    assert ShiftTotals.of(shift).expected == 5_000_000 - 1_250_000
