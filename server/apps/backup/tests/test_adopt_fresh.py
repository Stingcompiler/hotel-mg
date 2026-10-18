"""A clean reception PC may open a hotel from a backup even after the setup it asks for (decision 230)."""

import pytest
from django.conf import settings

from apps.accounts.models import User
from apps.backup import adopt
from apps.cash import services as cash
from apps.guests.models import Guest
from apps.rooms.models import Room, RoomType

pytestmark = pytest.mark.django_db


def _set_up_but_empty() -> User:
    """What a new reception PC looks like after the first steps: password changed, staff and rooms added."""
    manager = User.objects.create_user("manager", "المدير", role="manager", password="manager-pass-1", pin="1234")
    User.objects.create_user("ahmed", "أحمد", role="reception", password="pass-12345", pin="5678")
    single = RoomType.objects.create(
        name="مفردة", nightly_price=1_000_000, weekly_price=6_000_000, monthly_price=20_000_000
    )
    Room.objects.create(number="101", floor=1, room_type=single)
    return manager


def test_accounts_rooms_and_settings_do_not_close_the_door():
    _set_up_but_empty()
    assert adopt.is_fresh() is True


def test_a_guest_or_an_open_shift_means_the_pc_holds_hotel_data():
    manager = _set_up_but_empty()
    Guest.objects.create(full_name="محمد عثمان")
    assert adopt.is_fresh() is False
    Guest.objects.all().delete()  # test cleanup only; the app never deletes rows
    cash.open_shift(manager, opening=0)
    assert adopt.is_fresh() is False


def test_the_owner_pc_never_adopts(monkeypatch):
    monkeypatch.setattr(settings, "SKYTOWERS_ROLE", "owner")
    assert adopt.is_fresh() is False


def test_status_offers_it_to_a_manager_on_a_clean_pc():
    from rest_framework.test import APIClient

    from apps.accounts import services as accounts

    _set_up_but_empty()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {accounts.login_with_password('manager', 'manager-pass-1').token}")
    assert client.get("/api/v1/system/status").json()["can_adopt"] is True
