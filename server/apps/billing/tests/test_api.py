from datetime import timedelta

import pytest
import time_machine
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.billing.models import Folio, Payment
from apps.billing.services import FolioTotals, next_number
from apps.stays.models import Stay
from conftest import PASSWORD

pytestmark = pytest.mark.django_db


@pytest.fixture
def shift(reception_api):
    assert reception_api.post("/api/v1/shifts/open", {"opening": 5_000_000}, format="json").status_code == 201


def book(api, guest, room_type, room, **extra):
    payload = {
        "guest": str(guest.pk),
        "room_type": str(room_type.pk),
        "room": str(room.pk),
        "check_in_date": "2026-09-26",
        "duration_kind": "monthly",
        "count": 1,
        **extra,
    }
    res = api.post("/api/v1/reservations/", payload, format="json")
    return res


def folio_url(reservation_json):
    return f"/api/v1/folios/{reservation_json['folio']}"


def pay(api, r, amount, method="cash", reference=""):
    res = api.post(
        f"{folio_url(r)}/payments", {"amount": amount, "method": method, "reference": reference}, format="json"
    )
    assert res.status_code == 201, res.json()
    return res.json()


class TestBooking:
    def test_folio_invoice_numbers_are_sequential(self, reception_api, guest, double, rooms):
        a = book(reception_api, guest, double, rooms["202"]).json()
        b = book(reception_api, guest, double, rooms["205"]).json()
        assert (a["invoice"], b["invoice"]) == ("INV-000001", "INV-000002")

    def test_deposit_needs_open_shift(self, reception_api, guest, double, rooms):
        res = book(reception_api, guest, double, rooms["202"], deposit=10_000_000)
        assert res.status_code == 409 and res.json()["code"] == "no_open_shift"
        assert not Folio.objects.exists()  # the booking rolled back with it

    def test_deposit_and_discount_at_booking(self, reception_api, guest, double, rooms, shift):
        # Artboard 6.4 A: monthly 300,000 − discount 15,000, deposit 100,000 cash → total 285,000, remaining 185,000
        res = book(
            reception_api,
            guest,
            double,
            rooms["202"],
            discount=1_500_000,
            discount_reason="نزيل دائم — موافقة المدير شفهيًا",
            deposit=10_000_000,
            check_in_now=True,
        )
        assert res.status_code == 201, res.json()
        body = res.json()
        assert body["balance"] == 18_500_000
        folio = reception_api.get(folio_url(body)).json()
        assert folio["totals"] == {
            "charges": 30_000_000,
            "discounts": -1_500_000,
            "total": 28_500_000,
            "paid": 10_000_000,
            "balance": 18_500_000,
        }
        texts = [e["text"] for e in folio["ledger"]]
        assert texts[0] == "عربون — نقدي"  # taken at booking, before the charge was posted at check-in
        assert "إقامة شهرية — مزدوجة 202 (30 ليلة)" in texts
        assert "خصم: نزيل دائم — موافقة المدير شفهيًا" in texts

    def test_discount_needs_reason_and_manager_above_limit(self, reception_api, guest, double, rooms, manager):
        res = book(reception_api, guest, double, rooms["202"], discount=1_500_000)
        assert res.json()["code"] == "reason_required"
        res = book(reception_api, guest, double, rooms["202"], discount=9_000_000, discount_reason="شركة")
        assert res.status_code == 403 and res.json()["code"] == "override_required"
        res = book(
            reception_api,
            guest,
            double,
            rooms["202"],
            discount=9_000_000,
            discount_reason="شركة",
            manager_password=PASSWORD,
        )
        assert res.status_code == 201
        assert res.json()["rate_snapshot"]["discount"]["approved_by"] == str(manager.pk)

    def test_non_cash_needs_reference(self, reception_api, guest, double, rooms, shift):
        res = book(reception_api, guest, double, rooms["202"], deposit=1_000_000, deposit_method="bankak")
        assert res.json()["code"] == "reference_required"


def test_room_203_ledger_from_the_artboard(reception_api, manager_api, guest, double, rooms, shift):
    """Artboard 6.5 A: the invoice ledger ends at 15,000 remaining, with one reversed payment."""
    r = book(
        reception_api,
        guest,
        double,
        rooms["202"],
        discount=1_500_000,
        discount_reason="نزيل دائم",
        deposit=10_000_000,
        check_in_now=True,
    ).json()
    pay(reception_api, r, 12_000_000, "bankak", "BOK-77812")
    wrong = pay(reception_api, r, 5_000_000)
    res = reception_api.post(
        f"/api/v1/payments/{wrong['id']}/reverse", {"reason": "خطأ إدخال: المبلغ المستلم 40,000"}, format="json"
    )
    assert res.status_code == 201 and res.json()["amount"] == -5_000_000
    pay(reception_api, r, 4_000_000)
    pay(reception_api, r, 1_000_000, "transfer", "TRF-2210")

    folio = reception_api.get(folio_url(r)).json()
    assert [e["balance"] for e in folio["ledger"]][-1] == 1_500_000
    reversal = next(e for e in folio["ledger"] if e["kind"] == "reversal")
    assert reversal["debit"] == 5_000_000 and reversal["reverses"] == wrong["id"]
    assert folio["totals"]["paid"] == 27_000_000 and folio["totals"]["balance"] == 1_500_000
    again = reception_api.post(f"/api/v1/payments/{wrong['id']}/reverse", {"reason": "x"}, format="json")
    assert again.json()["code"] == "already_reversed"

    # Drawer: opening 50,000 + cash 100,000 + 50,000 − 50,000 (reversed) + 40,000 = 190,000; bankak/transfer excluded
    totals = reception_api.get("/api/v1/shifts/current").json()["totals"]
    assert totals["receipts"] == {"cash": 14_000_000, "bankak": 12_000_000, "transfer": 1_000_000, "total": 27_000_000}
    assert totals["expected"] == 19_000_000
    movements = reception_api.get("/api/v1/shifts/current").json()["movements"]
    assert any(m["text"].startswith("عربون — غرفة 202") for m in movements)


def test_service_line_and_reversal(reception_api, guest, double, rooms):
    r = book(reception_api, guest, double, rooms["202"], check_in_now=True).json()
    res = reception_api.post(
        f"{folio_url(r)}/lines", {"kind": "service", "description": "غسيل ملابس", "amount": 300_000}, format="json"
    )
    assert res.status_code == 201 and res.json()["totals"]["total"] == 30_300_000
    line = next(e for e in res.json()["ledger"] if e["text"] == "غسيل ملابس")
    res = reception_api.post(f"{folio_url(r)}/lines/{line['id']}/reverse", {"reason": "لم تُقدَّم"}, format="json")
    assert res.json()["totals"]["total"] == 30_000_000
    res = reception_api.post(f"{folio_url(r)}/lines", {"kind": "service", "amount": 1}, format="json")
    assert "description" in res.json()["errors"]


def test_checkout_with_debt_by_manager_override(reception_api, guest, double, rooms, manager, shift):
    """Artboard 6.5 C: leaves owing 15,000; the debt stays on the closed folio."""
    r = book(reception_api, guest, double, rooms["202"], check_in_now=True).json()
    pay(reception_api, r, 28_500_000)
    stay = Stay.objects.get(reservation_id=r["id"])
    url = f"/api/v1/stays/{stay.pk}/checkout"
    assert reception_api.post(url, {}, format="json").json()["balance"] == 1_500_000
    res = reception_api.post(
        url, {"override_password": PASSWORD, "override_reason": "النزيل سيسدد المتبقي غدًا صباحًا"}, format="json"
    )
    assert res.status_code == 200 and res.json()["override_by_name"] == "المدير"
    folio = Folio.objects.get(reservation_id=r["id"])
    assert folio.status == "closed" and FolioTotals.of(folio).balance == 1_500_000
    assert AuditLog.objects.get(action="stay.checkout").after["balance_at_checkout"] == 1_500_000
    pay(reception_api, r, 1_500_000)  # the debt can still be paid later
    assert FolioTotals.of(folio).balance == 0


def test_cancel_stay_refunds_excess_in_cash(reception_api, guest, double, rooms, manager):
    """V2 artboard 6.5 F: total 285,000, paid 270,000, 12 nights at 15,000 = 180,000 → refund 90,000."""
    with time_machine.travel(timezone.now() - timedelta(days=12)):
        r = book(
            reception_api,
            guest,
            double,
            rooms["202"],
            check_in_date="2026-09-14",
            discount=1_500_000,
            discount_reason="نزيل دائم",
            check_in_now=True,
        ).json()
    # Opened after the back-dated booking: a write "now" followed by one 12 days earlier trips the clock guard.
    assert reception_api.post("/api/v1/shifts/open", {"opening": 5_000_000}, format="json").status_code == 201
    pay(reception_api, r, 27_000_000)
    stay = Stay.objects.get(reservation_id=r["id"])
    res = reception_api.post(
        f"/api/v1/stays/{stay.pk}/cancel",
        {"reason": "سفر مفاجئ", "option_key": "m0w0d12", "override_password": PASSWORD},
        format="json",
    )
    assert res.status_code == 200, res.json()
    folio = reception_api.get(folio_url(r)).json()
    assert folio["totals"]["total"] == 18_000_000
    assert folio["totals"]["paid"] == 18_000_000 and folio["totals"]["balance"] == 0
    refund = Payment.objects.get(kind="refund")
    assert refund.amount == -9_000_000 and refund.method == "cash"
    assert res.json()["reservation"]["rate_snapshot"]["cancellation"]["refund"] == 9_000_000


def test_refund_cannot_exceed_credit(reception_api, guest, double, rooms, shift):
    r = book(reception_api, guest, double, rooms["202"], deposit=5_000_000).json()
    reception_api.post(f"/api/v1/reservations/{r['id']}/cancel", {"reason": "اعتذر"}, format="json")
    url = f"{folio_url(r)}/refunds"
    too_much = reception_api.post(url, {"amount": 6_000_000, "method": "cash", "reason": "ردّ العربون"}, format="json")
    assert too_much.json()["code"] == "refund_exceeds_credit"
    ok = reception_api.post(url, {"amount": 5_000_000, "method": "cash", "reason": "ردّ العربون"}, format="json")
    assert ok.status_code == 201 and ok.json()["kind"] == "refund"


def test_board_shows_balances(reception_api, guest, double, rooms, shift):
    r = book(reception_api, guest, double, rooms["202"], check_in_now=True).json()
    pay(reception_api, r, 28_500_000)
    board = reception_api.get("/api/v1/rooms/", {"view": "board"}).json()
    row = next(x for x in board["rooms"] if x["number"] == "202")
    assert row["stay"]["balance"] == 1_500_000 and row["stay"]["invoice"] == "INV-000001"


@pytest.mark.django_db(transaction=True)
def test_invoice_numbers_are_gap_free_across_rollbacks():
    with transaction.atomic():
        assert next_number("invoice") == 1
    with pytest.raises(RuntimeError), transaction.atomic():
        next_number("invoice")
        raise RuntimeError("rolled back")
    with transaction.atomic():
        assert next_number("invoice") == 2
    with pytest.raises(RuntimeError):
        next_number("invoice")  # outside a transaction
