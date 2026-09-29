"""Review 2026-09-29, batch 7: money and the owner-dashboard crash (A-1…A-4, A-11…A-18)."""

import pytest

from apps.billing import rules as billing_rules
from apps.billing.models import Folio, Payment
from apps.cash import rules as cash_rules
from conftest import PASSWORD

pytestmark = pytest.mark.django_db


@pytest.fixture
def shift(reception_api):
    assert reception_api.post("/api/v1/shifts/open", {"opening": 0}, format="json").status_code == 201


def book(api, guest, room_type, room=None, **extra):
    payload = {
        "guest": str(guest.pk),
        "room_type": str(room_type.pk),
        "check_in_date": "2026-09-26",
        "duration_kind": "daily",
        "count": 3,
        **extra,
    }
    if room is not None:
        payload["room"] = str(room.pk)
    res = api.post("/api/v1/reservations/", payload, format="json")
    assert res.status_code == 201, res.json()
    return res.json()


def test_rules():
    # 100,000 base; the folio charges 80,000 now (20 % off already): any further discount needs a manager.
    assert billing_rules.discount_needs_manager(10_000_000, 8_000_000, 1, 20)
    assert not billing_rules.discount_needs_manager(10_000_000, 10_000_000, 2_000_000, 20)
    assert not billing_rules.discount_needs_manager(10_000_000, 11_000_000, 2_000_000, 20)  # upgrade charges
    assert cash_rules.expense_reversal_needs_manager(False, False, False)
    assert not cash_rules.expense_reversal_needs_manager(True, False, False)
    assert not cash_rules.expense_reversal_needs_manager(False, True, False)
    assert not cash_rules.expense_reversal_needs_manager(False, False, True)
    assert cash_rules.reference_required("bankak") and not cash_rules.reference_required("cash")


def test_a_no_show_that_owes_money_no_longer_breaks_the_debts_report_or_the_dashboard(
    reception_api, manager_api, guest, single, rooms
):
    """A-1: a booking without a room, charged a service, then no-show — the report and the dashboard were a 500."""
    r = book(reception_api, guest, single)
    lines = f"/api/v1/folios/{r['folio']}/lines"
    res = reception_api.post(lines, {"kind": "service", "description": "حجز مؤكد", "amount": 6_000_000}, format="json")
    assert res.status_code == 201, res.json()
    assert reception_api.post(f"/api/v1/reservations/{r['id']}/no-show", {}, format="json").status_code == 200
    report = manager_api.get("/api/v1/reports/debts", {"status": "all"})
    assert report.status_code == 200, report.json()
    row = next(x for x in report.json()["rows"] if x["balance"] == 6_000_000)
    assert row["room"] == "—" and "بدين" in row["reason"]
    dashboard = manager_api.get("/api/v1/reports/owner-dashboard")
    assert dashboard.status_code == 200, dashboard.json()
    assert dashboard.json()["kpis"]["debts"]["largest"]["room"] == "—"


def test_no_discount_then_refund_on_a_closed_folio_without_a_manager(
    reception_api, manager_api, guest, double, rooms, manager, shift
):
    """A-2: a cancelled stay settled to zero; a discount made credit that reception paid out in cash."""
    r = book(reception_api, guest, double, rooms["202"], check_in_now=True)
    folio = f"/api/v1/folios/{r['folio']}"
    reception_api.post(f"{folio}/payments", {"amount": 4_500_000, "method": "cash"}, format="json")
    stay = reception_api.get(f"/api/v1/reservations/{r['id']}").json()["stay"]
    body = {"reason": "سفر", "option_key": "m0w0d1", "override_password": PASSWORD}
    assert reception_api.post(f"/api/v1/stays/{stay}/cancel", body, format="json").status_code == 200
    assert Folio.objects.get(pk=r["folio"]).status == "closed"
    discount = {"kind": "discount", "description": "", "amount": 500_000, "reason": "مجاملة"}
    res = reception_api.post(f"{folio}/lines", discount, format="json")
    assert res.status_code == 403 and res.json()["code"] == "override_required"


def test_a_price_cut_and_a_later_folio_discount_share_one_limit(reception_api, guest, single, rooms, shift):
    """A-4: 20 % off at booking, then 20 % of what is left on the folio = 36 % without a manager."""
    body = {"count": 10, "option_key": "m0w1d3", "final_total": 9_040_000, "override_reason": "اتفاق"}
    r = book(reception_api, guest, single, rooms["101"], check_in_now=True, **body)
    discount = {"kind": "discount", "description": "", "amount": 1_808_000, "reason": "مجاملة"}
    res = reception_api.post(f"/api/v1/folios/{r['folio']}/lines", discount, format="json")
    assert res.status_code == 403 and res.json()["code"] == "override_required"


def test_extending_or_moving_cannot_overbook_a_room_type(reception_api, guest, single, double, rooms, manager):
    """A-3: the room-type capacity (BIZ-8) held for bookings only; extend and change room skipped it."""
    stay = book(reception_api, guest, single, rooms["101"], check_in_now=True)["stay"]  # nights 26–28
    for room in (None, None, rooms["102"]):
        book(reception_api, guest, single, room, check_in_date="2026-09-29", count=1)
    res = reception_api.post(f"/api/v1/stays/{stay}/extend", {"duration_kind": "daily", "count": 1}, format="json")
    assert res.status_code == 409 and res.json()["code"] == "room_unavailable"

    book(reception_api, guest, double)
    book(reception_api, guest, double)  # both doubles taken tonight, no room chosen yet
    move = {"room": str(rooms["202"].pk), "reason": "طلب النزيل", "override_password": PASSWORD}
    res = reception_api.post(f"/api/v1/stays/{stay}/change-room", move, format="json")
    assert res.status_code == 409 and res.json()["code"] == "room_unavailable"


def test_expense_reversal_and_reference_rules(reception_api, manager_api, manager, shift):
    """A-14: someone else's expense needs a manager to reverse; A-15: Bankak and transfers need a reference."""
    body = {"category": "supplies", "amount": 1_000_000, "note": "مواد تنظيف", "method": "cash"}
    theirs = manager_api.post("/api/v1/expenses/", body, format="json").json()
    mine = reception_api.post("/api/v1/expenses/", body, format="json").json()
    res = reception_api.post(f"/api/v1/expenses/{theirs['id']}/reverse", {"reason": "خطأ"}, format="json")
    assert res.status_code == 403 and res.json()["code"] == "override_required"
    ok = {"reason": "خطأ", "manager_password": PASSWORD}
    assert reception_api.post(f"/api/v1/expenses/{theirs['id']}/reverse", ok, format="json").status_code == 201
    own = reception_api.post(f"/api/v1/expenses/{mine['id']}/reverse", {"reason": "خطأ"}, format="json")
    assert own.status_code == 201
    res = reception_api.post("/api/v1/expenses/", {**body, "method": "bankak"}, format="json")
    assert res.status_code == 400 and res.json()["code"] == "reference_required"


def test_revenue_nets_a_reversed_discount_and_has_a_column_for_other_currencies(
    reception_api, manager_api, guest, double, rooms, shift
):
    """A-16 (and A-8): the discount tile and column counted reversed discounts; foreign money has its own column."""
    r = book(reception_api, guest, double, rooms["202"], check_in_now=True, discount=300_000, discount_reason="دائم")
    folio = reception_api.get(f"/api/v1/folios/{r['folio']}").json()
    line = next(e for e in folio["ledger"] if e["kind"] == "discount")
    url = f"/api/v1/folios/{r['folio']}/lines/{line['id']}/reverse"
    assert manager_api.post(url, {"reason": "خطأ"}, format="json").status_code == 200
    report = manager_api.get("/api/v1/reports/revenue", {"date_from": "2026-09-26"}).json()
    assert report["meta"]["totals"]["discounts"] == 0
    assert "foreign" in [c["key"] for c in report["columns"]]


def test_cancel_options_give_the_real_refund_and_the_refund_can_go_to_bankak(
    reception_api, guest, double, rooms, manager, shift
):
    """A-11: the dialog computed the refund without services; A-12: the refund could only be cash."""
    r = book(reception_api, guest, double, rooms["202"], check_in_now=True)  # 3 × 15,000
    folio = f"/api/v1/folios/{r['folio']}"
    reception_api.post(f"{folio}/lines", {"kind": "service", "description": "غسيل", "amount": 500_000}, format="json")
    reception_api.post(f"{folio}/payments", {"amount": 5_000_000, "method": "cash"}, format="json")
    stay = reception_api.get(f"/api/v1/reservations/{r['id']}").json()["stay"]
    options = reception_api.get(f"/api/v1/stays/{stay}/cancel").json()
    assert (options["services_total"], options["paid"]) == (500_000, 5_000_000)
    body = {
        "reason": "سفر",
        "option_key": "m0w0d1",
        "override_password": PASSWORD,
        "refund_method": "bankak",
        "refund_reference": "BOK-99",
    }
    assert reception_api.post(f"/api/v1/stays/{stay}/cancel", body, format="json").status_code == 200
    refund = Payment.objects.get(folio_id=r["folio"], kind="refund")
    # 50,000 paid − (15,000 for the night + 5,000 laundry) = 30,000 back
    assert (refund.amount, refund.method, refund.reference) == (-3_000_000, "bankak", "BOK-99")
