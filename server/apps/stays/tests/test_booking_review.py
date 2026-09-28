"""Booking flow review (2026-09-28): one discount limit for price cut plus discount."""

import pytest

from apps.stays.models import Reservation
from conftest import PASSWORD

pytestmark = pytest.mark.django_db


def book(api, guest, room_type, room, **extra):
    payload = {
        "guest": str(guest.pk),
        "room_type": str(room_type.pk),
        "room": str(room.pk),
        "check_in_date": "2026-09-27",
        "duration_kind": "daily",
        "count": 10,
        "option_key": "m0w1d3",  # 113,000
        **extra,
    }
    return api.post("/api/v1/reservations/", payload, format="json")


def test_price_cut_and_discount_add_up_against_one_limit(reception_api, guest, single, rooms, manager):
    """15 % off the price and 15 % off that again is 28 % — beyond the 20 % limit even though each part is within it."""
    body = {
        "final_total": 9_600_000,
        "override_reason": "اتفاق",
        "discount": 1_440_000,
        "discount_reason": "عرض",
    }
    res = book(reception_api, guest, single, rooms["101"], **body)
    assert res.status_code == 403 and res.json()["code"] == "override_required"
    assert not Reservation.objects.exists()
    res = book(reception_api, guest, single, rooms["101"], **body, manager_password=PASSWORD)
    assert res.status_code == 201, res.json()
    snapshot = Reservation.objects.get().rate_snapshot
    assert snapshot["override_approved_by"] == snapshot["discount"]["approved_by"] == str(manager.pk)


def test_within_the_limit_together_needs_no_manager(reception_api, guest, single, rooms):
    body = {"final_total": 10_700_000, "override_reason": "اتفاق", "discount": 700_000, "discount_reason": "عرض"}
    assert book(reception_api, guest, single, rooms["101"], **body).status_code == 201  # 12 % off in total


def test_discount_above_the_price_is_refused(reception_api, guest, single, rooms):
    res = book(reception_api, guest, single, rooms["101"], discount=11_400_000, discount_reason="x")
    assert res.status_code == 400 and res.json()["code"] == "validation_error"
