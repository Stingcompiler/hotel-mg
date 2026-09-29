"""Review 2026-09-29, batch 11: early departure (owner decision 4) and the cancel settlement (A-5)."""

from datetime import timedelta

import time_machine
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.billing.models import Folio, Payment
from apps.billing.services import FolioTotals
from apps.stays.models import Stay

from .test_stays import walk_in


def _stay(r):
    return Stay.objects.get(reservation_id=r["id"])


def test_early_departure_charges_the_nights_used_and_refunds_the_rest(
    reception_api, guest, single, rooms, open_shift, pay
):
    with time_machine.travel(timezone.now() - timedelta(days=1)):  # 3 nights × 12,000 from yesterday
        r = walk_in(reception_api, guest, single, rooms["101"], check_in_date="2026-09-25")
        pay(reception_api, r["id"])
    stay = _stay(r)
    url = f"/api/v1/stays/{stay.pk}/checkout"
    quote = reception_api.get(url).json()["early_departure"]
    assert quote == {
        "nights_used": 1,
        "nights_booked": 3,
        "room_charges": 3_600_000,
        "new_room_charges": 1_200_000,
        "services": 0,
        "paid": 3_600_000,
        "refund": 2_400_000,
        "balance_after": 0,
    }
    res = reception_api.post(url, {"refund_method": "cash"}, format="json")
    assert res.status_code == 200, res.json()
    folio = Folio.objects.get(reservation_id=r["id"])
    totals = FolioTotals.of(folio)
    assert (totals.total, totals.paid, totals.balance) == (1_200_000, 1_200_000, 0)
    refund = Payment.objects.get(folio=folio, kind="refund")
    assert refund.amount == -2_400_000 and refund.shift_id == open_shift.pk
    assert res.json()["reservation"]["status"] == "checked_out"
    assert res.json()["reservation"]["total"] == 1_200_000
    assert AuditLog.objects.get(action="stay.checkout").after["early_departure"]["refund"] == 2_400_000


def test_leaving_on_the_booked_day_is_not_an_early_departure(reception_api, guest, single, rooms, open_shift, pay):
    with time_machine.travel(timezone.now() - timedelta(days=3)):
        r = walk_in(reception_api, guest, single, rooms["101"], check_in_date="2026-09-23")
        pay(reception_api, r["id"])
    stay = _stay(r)
    assert reception_api.get(f"/api/v1/stays/{stay.pk}/checkout").json() == {"early_departure": None}
    assert reception_api.post(f"/api/v1/stays/{stay.pk}/checkout", {}, format="json").status_code == 200
    assert not Payment.objects.filter(folio__reservation_id=r["id"], kind="refund").exists()


def test_the_cancel_options_never_exceed_the_stay(reception_api, guest, single, rooms):
    with time_machine.travel(timezone.now() - timedelta(days=1)):  # 2 nights = 24,000 from yesterday
        r = walk_in(reception_api, guest, single, rooms["101"], check_in_date="2026-09-25", count=2)
    stay = _stay(r)
    options = reception_api.get(f"/api/v1/stays/{stay.pk}/cancel").json()["options"]
    assert options[0]["key"] == "paid" and options[0]["total"] == 1_200_000
    assert all(o["total"] <= 2_400_000 for o in options)


def test_an_overdue_stay_is_extended_before_moving_to_another_type(reception_api, guest, single, rooms):
    """A-17: no booked night was left to price the difference on, so the upgrade was free."""
    with time_machine.travel(timezone.now() - timedelta(days=3)):
        r = walk_in(reception_api, guest, single, rooms["101"], check_in_date="2026-09-23", count=1)
    url = f"/api/v1/stays/{_stay(r).pk}/change-room"
    res = reception_api.post(url, {"room": str(rooms["202"].pk), "reason": "طلب النزيل"}, format="json")
    assert res.status_code == 409 and res.json()["code"] == "stay_overdue"
    res = reception_api.post(url, {"room": str(rooms["102"].pk), "reason": "تكييف معطل"}, format="json")
    assert res.status_code == 200, res.json()  # the same type: nothing to price
