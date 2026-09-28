import pytest

from apps.stays.models import Stay
from apps.stays.tests.conftest import double, frozen_today, guest, rooms, single  # noqa: F401


@pytest.fixture
def monthly_stay(reception_api, guest, double, rooms):  # noqa: F811 — the stays fixtures above
    """Walk-in 26 Sep, monthly: last night 25 Oct → first alert 20 Oct 09:00, second 23 Oct 09:00."""
    payload = {
        "guest": str(guest.pk),
        "room_type": str(double.pk),
        "room": str(rooms["202"].pk),
        "check_in_date": "2026-09-26",
        "duration_kind": "monthly",
        "count": 1,
        "check_in_now": True,
    }
    res = reception_api.post("/api/v1/reservations/", payload, format="json")
    assert res.status_code == 201, res.json()
    return Stay.objects.get(reservation_id=res.json()["id"])
