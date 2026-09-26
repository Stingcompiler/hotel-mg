from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
import time_machine

from apps.guests.models import Guest
from apps.rooms.models import Room, RoomType

TODAY = date(2026, 9, 26)


@pytest.fixture(autouse=True)
def frozen_today():
    """Saturday 26 September 2026, 10:00 in Khartoum — the date of the design's artboards."""
    with time_machine.travel(datetime(2026, 9, 26, 10, 0, tzinfo=ZoneInfo("Africa/Khartoum")), tick=True):
        yield


@pytest.fixture
def single(db):
    return RoomType.objects.create(
        name="مفردة", capacity=1, nightly_price=1_200_000, weekly_price=7_700_000, monthly_price=28_000_000
    )


@pytest.fixture
def double(db):
    return RoomType.objects.create(
        name="مزدوجة", capacity=2, nightly_price=1_500_000, weekly_price=9_500_000, monthly_price=30_000_000
    )


@pytest.fixture
def rooms(single, double):
    made = {n: Room.objects.create(number=n, floor=int(n[0]), room_type=single) for n in ("101", "102", "106")}
    made |= {n: Room.objects.create(number=n, floor=int(n[0]), room_type=double) for n in ("202", "205")}
    return made


@pytest.fixture
def guest(db):
    return Guest.objects.create(full_name="خالد إبراهيم عبدالله", search_name="خالد ابراهيم عبدالله")


@pytest.fixture
def open_shift(reception):
    from apps.cash import services as cash

    return cash.open_shift(reception, opening=5_000_000)


@pytest.fixture
def pay():
    """Pay a reservation's full balance in cash through the API."""

    def settle(api, reservation_id):
        from apps.billing.models import Folio
        from apps.billing.services import FolioTotals

        folio = Folio.objects.get(reservation_id=reservation_id)
        due = FolioTotals.of(folio).balance
        res = api.post(f"/api/v1/folios/{folio.pk}/payments", {"amount": due, "method": "cash"}, format="json")
        assert res.status_code == 201, res.json()
        return res.json()

    return settle
