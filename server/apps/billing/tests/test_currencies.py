"""Payments in other currencies at the owner's rate (owner decision 2026-09-28)."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.services import login_with_password
from apps.billing import rules
from apps.billing.models import Payment
from conftest import PASSWORD

pytestmark = pytest.mark.django_db


def test_rules():
    assert rules.to_base(15_000, 250_000) == 37_500_000  # 150.00 $ at 2,500 → 375,000 ج.س
    assert rules.to_base(1, 250_050) == 2_501  # half a piaster rounds away from zero
    assert rules.to_base(-15_000, 250_000) == -37_500_000
    assert rules.foreign_text(15_000, "$") == "150 $"
    assert rules.foreign_text(15_050, "$") == "150.50 $"
    assert rules.foreign_text(-2_000, "USD") == "-20 USD"
    assert rules.rate_text(250_000) == "2,500"
    assert rules.rate_text(250_050) == "2,500.50"
    assert rules.valid_currency_code("USD", "SDG")
    assert not rules.valid_currency_code("SDG", "SDG")
    assert not rules.valid_currency_code("us", "SDG")
    assert not rules.valid_currency_code("دولا", "SDG")
    assert not rules.valid_currency_code("US1", "SDG")
    rows = [
        ("USD", "cash", 10_000, 25_000_000),
        ("USD", "transfer", 5_000, 12_500_000),
        ("EUR", "cash", 1_000, 2_900_000),
    ]
    assert rules.foreign_totals(rows) == {
        "USD": {"cash": 10_000, "total": 15_000, "base": 37_500_000},
        "EUR": {"cash": 1_000, "total": 1_000, "base": 2_900_000},
    }


@pytest.fixture
def owner_api(make_user):
    owner = make_user("owner", role="owner", full_name="المالك")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {login_with_password(owner.username, PASSWORD).token}")
    return client


@pytest.fixture
def usd(owner_api):
    body = {"code": "usd", "name": "دولار أمريكي", "symbol": "$", "rate": 250_000}
    res = owner_api.post("/api/v1/currencies/", body, format="json")
    assert res.status_code == 201, res.json()
    return res.json()


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
    assert res.status_code == 201, res.json()
    return res.json()


def test_only_the_owner_sets_currencies(owner_api, manager_api, reception_api, usd):
    assert usd["code"] == "USD" and usd["rate"] == 250_000
    body = {"code": "EUR", "name": "يورو", "rate": 290_000}
    assert manager_api.post("/api/v1/currencies/", body, format="json").status_code == 403
    assert [c["code"] for c in reception_api.get("/api/v1/currencies/").json()] == ["USD"]
    again = {"code": "USD", "name": "x", "rate": 1}
    assert owner_api.post("/api/v1/currencies/", again, format="json").status_code == 400  # change its rate instead
    base = {"code": "SDG", "name": "x", "rate": 1}
    assert owner_api.post("/api/v1/currencies/", base, format="json").status_code == 400
    url = f"/api/v1/currencies/{usd['id']}"
    res = owner_api.patch(url, {"version": usd["version"], "rate": 260_000}, format="json")
    assert res.status_code == 200 and res.json()["rate"] == 260_000
    assert manager_api.patch(url, {"version": 2, "rate": 1}, format="json").status_code == 403


def test_a_dollar_payment_keeps_its_rate_and_stays_out_of_the_pounds_drawer(
    owner_api, reception_api, guest, double, rooms, usd
):
    assert reception_api.post("/api/v1/shifts/open", {"opening": 5_000_000}, format="json").status_code == 201
    deposit = {"deposit_currency": "USD", "deposit_foreign_amount": 4_000}  # 40 $
    r = book(reception_api, guest, double, rooms["202"], check_in_now=True, **deposit)
    folio = f"/api/v1/folios/{r['folio']}"
    body = {"method": "cash", "currency": "USD", "foreign_amount": 15_000}
    res = reception_api.post(f"{folio}/payments", body, format="json")
    assert res.status_code == 201, res.json()
    paid = res.json()
    got = (paid["amount"], paid["currency"], paid["foreign_amount"], paid["rate"])
    assert got == (37_500_000, "USD", 15_000, 250_000)

    # A later rate never changes what was received.
    owner_api.patch(f"/api/v1/currencies/{usd['id']}", {"version": usd["version"], "rate": 300_000}, format="json")
    detail = reception_api.get(folio).json()
    assert detail["totals"]["paid"] == 10_000_000 + 37_500_000
    assert any("(150 $ بسعر 2,500)" in e["text"] for e in detail["ledger"])

    totals = reception_api.get("/api/v1/shifts/current").json()["totals"]
    assert totals["receipts"]["cash"] == 0 and totals["expected"] == 5_000_000  # no pounds came in
    usd_row = {
        "currency": "USD",
        "symbol": "$",
        "cash": 19_000,
        "total": 19_000,
        "base": 47_500_000,
        "opening": 0,
        "expected": 19_000,  # dollars in the drawer (A-7)
    }
    assert totals["foreign"] == [usd_row]
    movements = reception_api.get("/api/v1/shifts/current").json()["movements"]
    assert any("(150 $ بسعر 2,500)" in m["text"] for m in movements)

    undo = reception_api.post(f"/api/v1/payments/{paid['id']}/reverse", {"reason": "خطأ"}, format="json")
    assert undo.status_code == 201, undo.json()
    reversal = Payment.objects.get(reverses_id=paid["id"])
    assert (reversal.amount, reversal.currency, reversal.foreign_amount, reversal.rate) == (
        -37_500_000,
        "USD",
        -15_000,
        250_000,
    )


def test_the_receipt_says_what_was_handed_over(reception_api, guest, double, rooms, usd):
    from apps.reports import documents

    reception_api.post("/api/v1/shifts/open", {"opening": 0}, format="json")
    r = book(reception_api, guest, double, rooms["202"], check_in_now=True)
    body = {"method": "cash", "currency": "USD", "foreign_amount": 15_050}
    paid = reception_api.post(f"/api/v1/folios/{r['folio']}/payments", body, format="json").json()
    doc = documents.payment_receipt(Payment.objects.get(pk=paid["id"]))
    assert doc["paid_in"] == "150.50 $ بسعر 2,500" and doc["amount"] == 37_625_000


def test_inactive_or_unknown_currency_is_refused(owner_api, reception_api, guest, double, rooms, usd):
    reception_api.post("/api/v1/shifts/open", {"opening": 0}, format="json")
    owner_api.patch(f"/api/v1/currencies/{usd['id']}", {"version": usd["version"], "is_active": False}, format="json")
    r = book(reception_api, guest, double, rooms["202"], duration_kind="daily")
    url = f"/api/v1/folios/{r['folio']}/payments"
    for body in ({"currency": "USD", "foreign_amount": 100}, {"currency": "EUR", "foreign_amount": 100}):
        assert reception_api.post(url, {"method": "cash", **body}, format="json").status_code == 400
    res = reception_api.post(url, {"method": "cash", "currency": "USD"}, format="json")
    assert res.status_code == 400 and "foreign_amount" in res.json()["errors"]
    assert reception_api.post(url, {"method": "cash"}, format="json").status_code == 400


def test_dollars_are_refunded_counted_handed_over_and_carried_to_the_next_shift(
    owner_api, reception_api, guest, double, rooms, usd
):
    """Review 2026-09-29, A-6/A-7: the dollar drawer is refunded from, counted at close, handed over, and the next
    opening is checked against what was left."""
    assert reception_api.post("/api/v1/shifts/open", {"opening": 1_000_000}, format="json").status_code == 201
    r = book(reception_api, guest, double, rooms["202"], check_in_now=True)
    folio = f"/api/v1/folios/{r['folio']}"
    body = {"method": "cash", "currency": "USD", "foreign_amount": 20_000}  # 200 $ = 500,000
    assert reception_api.post(f"{folio}/payments", body, format="json").status_code == 201
    back = {"method": "cash", "currency": "USD", "foreign_amount": 4_000, "reason": "دفع زائد"}  # 40 $ back
    res = reception_api.post(f"{folio}/refunds", back, format="json")
    assert res.status_code == 201, res.json()
    assert (res.json()["amount"], res.json()["foreign_amount"]) == (-10_000_000, -4_000)

    usd_row = reception_api.get("/api/v1/shifts/current").json()["totals"]["foreign"][0]
    assert (usd_row["cash"], usd_row["expected"]) == (16_000, 16_000)
    assert reception_api.get("/api/v1/shifts/current").json()["totals"]["expected"] == 1_000_000  # pounds untouched

    close = {"counted": 1_000_000, "counted_foreign": {"USD": 15_000}}
    res = reception_api.post("/api/v1/shifts/close", close, format="json")
    assert res.json()["code"] == "reason_required" and res.json()["foreign_differences"] == {"USD": -1_000}
    handover = {"handed_over": 400_000, "handed_over_foreign": {"USD": 10_000}}
    too_much = {**close, "counted_foreign": {"USD": 16_000}, "handed_over_foreign": {"USD": 20_000}}
    assert reception_api.post("/api/v1/shifts/close", too_much, format="json").status_code == 400
    res = reception_api.post(
        "/api/v1/shifts/close", {**close, **handover, "difference_reason": "10 $ صُرفت خطأ"}, format="json"
    )
    assert res.status_code == 200, res.json()
    shift = res.json()
    assert shift["expected_foreign"] == {"USD": 16_000} and shift["counted_foreign"] == {"USD": 15_000}
    assert shift["handed_over"] == 400_000 and shift["handed_over_foreign"] == {"USD": 10_000}

    current = reception_api.get("/api/v1/shifts/current").json()
    assert current["suggested_opening"] == 600_000 and current["suggested_opening_foreign"] == {"USD": 5_000}
    res = reception_api.post("/api/v1/shifts/open", {"opening": 600_000}, format="json")
    assert res.status_code == 400 and res.json()["expected_foreign"] == {"USD": 5_000}  # 50 $ went missing
    opened = {"opening": 600_000, "opening_foreign": {"USD": 5_000}}
    res = reception_api.post("/api/v1/shifts/open", opened, format="json")
    assert res.status_code == 201 and res.json()["opening_expected"] == 600_000
    usd_row = reception_api.get("/api/v1/shifts/current").json()["totals"]["foreign"][0]
    assert (usd_row["opening"], usd_row["expected"]) == (5_000, 5_000)
    tiles = owner_api.get("/api/v1/reports/revenue").json()["meta"]["tiles"]
    assert {"label": "المحصّل دولار أمريكي", "value": "160 $", "type": "text"} in tiles  # A-8: in its currency
    statement = reception_api.get(f"/api/v1/shifts/{shift['id']}/statement").json()
    assert statement["currencies"] == [
        {
            "currency": "USD",
            "symbol": "$",
            "opening": 0,
            "received": 16_000,
            "expected": 16_000,
            "counted": 15_000,
            "difference": -1_000,
            "handed_over": 10_000,
            "base": 40_000_000,
        }
    ]  # A-9 / D-1: the dollars have their own line on the printed statement
    assert (statement["handed_over"], statement["left_in_drawer"]) == (400_000, 600_000)
