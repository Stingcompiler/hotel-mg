"""Review 2026-09-28, batch 2: money and business rules (BIZ-1…8, BIZ-13, SEC-1)."""

from datetime import timedelta

import pytest
import time_machine
from django.utils import timezone

from apps.accounts.services import login_with_password
from apps.audit.models import AuditLog
from apps.billing.models import Folio
from apps.billing.services import FolioTotals
from apps.guests import stats
from apps.rooms.models import Room
from apps.stays.models import Reservation, Stay
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
    return api.post("/api/v1/reservations/", payload, format="json")


def walk_in(api, guest, room_type, room, **extra):
    res = book(api, guest, room_type, room, check_in_now=True, **extra)
    assert res.status_code == 201, res.json()
    return res.json()


def stay_of(r) -> Stay:
    return Stay.objects.get(reservation_id=r["id"])


def ledger_entry(api, r, kind):
    folio = api.get(f"/api/v1/folios/{r['folio']}").json()
    return next(e for e in folio["ledger"] if e["kind"] == kind)


class TestRoomChangePricing:
    def test_whole_stay_priced_after_an_extension_and_a_second_move(
        self, reception_api, guest, single, double, rooms, manager
    ):
        """BIZ-1: the extension's nights are repriced too; BIZ-2: a second move starts from the current type."""
        stay = stay_of(walk_in(reception_api, guest, single, rooms["101"]))  # 3 nights, 36,000
        res = reception_api.post(
            f"/api/v1/stays/{stay.pk}/extend", {"duration_kind": "daily", "count": 2}, format="json"
        )
        assert res.json()["reservation"]["total"] == 6_000_000  # 5 nights × 12,000

        url = f"/api/v1/stays/{stay.pk}/change-room"
        res = reception_api.post(url, {"room": str(rooms["202"].pk), "reason": "طلب النزيل"}, format="json")
        assert res.status_code == 200, res.json()
        assert res.json()["reservation"]["total"] == 7_500_000  # 5 nights × 15,000

        back = {"room": str(rooms["102"].pk), "reason": "طلب النزيل"}
        res = reception_api.post(url, back, format="json")
        assert res.status_code == 403 and res.json()["difference"] == -1_500_000
        res = reception_api.post(
            url, {**back, "override_password": PASSWORD, "override_reason": "عودة للمفردة"}, format="json"
        )
        assert res.status_code == 200, res.json()
        assert res.json()["reservation"]["total"] == 6_000_000


class TestPriceApproval:
    def test_booking_far_below_base_needs_the_manager(self, reception_api, guest, single, rooms, manager):
        """BIZ-3: reception cannot type any price; beyond the discount limit the manager approves."""
        body = {"count": 10, "option_key": "m0w1d3", "final_total": 5_000_000, "override_reason": "اتفاق"}
        res = book(reception_api, guest, single, rooms["101"], **body)
        assert res.status_code == 403 and res.json()["code"] == "override_required"
        res = book(reception_api, guest, single, rooms["101"], **body, manager_password=PASSWORD)
        assert res.status_code == 201, res.json()
        snapshot = Reservation.objects.get(pk=res.json()["id"]).rate_snapshot
        assert snapshot["override_approved_by"] == str(manager.pk)

    def test_zero_price_is_refused(self, reception_api, guest, single, rooms):
        """BIZ-4: final_total 0 would book a free stay."""
        res = book(reception_api, guest, single, rooms["101"], final_total=0, override_reason="x")
        assert res.status_code == 400 and "final_total" in res.json()["errors"]

    def test_extension_below_base_needs_the_manager_and_shows_in_adjustments(
        self, reception_api, manager_api, guest, single, rooms, manager
    ):
        stay = stay_of(walk_in(reception_api, guest, single, rooms["101"]))
        url = f"/api/v1/stays/{stay.pk}/extend"
        body = {"duration_kind": "daily", "count": 2, "final_total": 1_000_000, "override_reason": "نزيل دائم"}
        res = reception_api.post(url, body, format="json")
        assert res.status_code == 403 and res.json()["code"] == "override_required"
        res = reception_api.post(url, {**body, "override_password": PASSWORD}, format="json")
        assert res.status_code == 200, res.json()
        extension = res.json()["reservation"]["rate_snapshot"]["extensions"][-1]
        assert extension["approved_by"] == str(manager.pk)

        rows = manager_api.get("/api/v1/reports/adjustments", {"date_from": "2026-09-26"}).json()["rows"]
        row = next(r for r in rows if r["type"] == "سعر تمديد معدَّل")
        assert row["amount"] == 1_000_000 - 2_400_000 and row["reason"] == "نزيل دائم"


class TestReversals:
    def test_room_line_reversal_needs_the_manager(self, reception_api, manager_api, guest, double, rooms, manager):
        """SEC-1: reception could erase a room charge alone."""
        r = walk_in(reception_api, guest, double, rooms["202"])
        line = ledger_entry(reception_api, r, "room")
        url = f"/api/v1/folios/{r['folio']}/lines/{line['id']}/reverse"
        res = reception_api.post(url, {"reason": "خطأ"}, format="json")
        assert res.status_code == 403 and res.json()["code"] == "override_required"
        res = reception_api.post(url, {"reason": "خطأ", "manager_password": "wrong"}, format="json")
        assert res.json()["code"] == "override_invalid"
        res = reception_api.post(url, {"reason": "خطأ", "manager_password": PASSWORD}, format="json")
        assert res.status_code == 200, res.json()
        assert res.json()["totals"]["total"] == 0
        assert AuditLog.objects.get(action="folio.reverse_line").after["approved_by"] == str(manager.pk)

    def test_manager_reverses_a_discount_and_totals_net_it(self, reception_api, manager_api, guest, double, rooms):
        """BIZ-7: a reversed discount no longer counts as a discount."""
        r = walk_in(reception_api, guest, double, rooms["202"], discount=500_000, discount_reason="نزيل دائم")
        line = ledger_entry(reception_api, r, "discount")
        url = f"/api/v1/folios/{r['folio']}/lines/{line['id']}/reverse"
        assert manager_api.post(url, {"reason": "خطأ"}, format="json").status_code == 200
        totals = FolioTotals.of(Folio.objects.get(pk=r["folio"]))
        assert totals.discounts == 0 and totals.total == 4_500_000

    def test_someone_elses_payment_needs_the_manager(self, reception_api, make_user, guest, double, rooms, shift):
        r = walk_in(reception_api, guest, double, rooms["202"])
        paid = reception_api.post(
            f"/api/v1/folios/{r['folio']}/payments", {"amount": 1_000_000, "method": "cash"}, format="json"
        ).json()
        other = make_user("sara", full_name="سارة")
        other_api = reception_api.__class__()
        other_api.credentials(HTTP_AUTHORIZATION=f"Token {login_with_password(other.username, PASSWORD).token}")
        url = f"/api/v1/payments/{paid['id']}/reverse"
        res = other_api.post(url, {"reason": "خطأ"}, format="json")
        assert res.status_code == 403 and res.json()["code"] == "override_required"
        make_user("manager", role="manager", full_name="المدير")
        res = other_api.post(url, {"reason": "خطأ", "manager_password": PASSWORD}, format="json")
        assert res.status_code == 201, res.json()


def test_cancel_nets_reversed_services_and_the_debt_counts(reception_api, guest, double, rooms, manager):
    """BIZ-5: a reversed service is not charged again at cancellation; BIZ-6: a cancelled stay's debt counts."""
    with time_machine.travel(timezone.now() - timedelta(days=12)):
        r = walk_in(
            reception_api, guest, double, rooms["202"], check_in_date="2026-09-14", duration_kind="monthly", count=1
        )
    lines = f"/api/v1/folios/{r['folio']}/lines"
    reception_api.post(lines, {"kind": "service", "description": "غسيل ملابس", "amount": 300_000}, format="json")
    service = ledger_entry(reception_api, r, "service")
    undo = reception_api.post(f"{lines}/{service['id']}/reverse", {"reason": "لم تُقدَّم"}, format="json")
    assert undo.status_code == 200
    stay = stay_of(r)
    res = reception_api.post(
        f"/api/v1/stays/{stay.pk}/cancel",
        {"reason": "سفر مفاجئ", "option_key": "m0w0d12", "override_password": PASSWORD},
        format="json",
    )
    assert res.status_code == 200, res.json()
    assert FolioTotals.of(Folio.objects.get(pk=r["folio"])).total == 18_000_000

    row = stats.for_guests([guest.pk])[guest.pk]
    assert row["debt"] == 18_000_000 and row["stays_count"] == 0
    assert guest.pk in stats.debtor_ids()


def test_bookings_without_a_room_cannot_exceed_the_type(reception_api, guest, single, rooms):
    """BIZ-8: three single rooms → a fourth single booking for the same nights is refused."""
    for _ in range(3):
        assert book(reception_api, guest, single, check_in_date="2026-09-27").status_code == 201
    res = book(reception_api, guest, single, check_in_date="2026-09-28")
    assert res.status_code == 409 and res.json()["code"] == "room_unavailable"
    res = book(reception_api, guest, single, rooms["106"], check_in_date="2026-09-27")
    assert res.status_code == 409
    assert book(reception_api, guest, single, check_in_date="2026-09-30").status_code == 201
    Room.objects.filter(number="106").update(in_service=False)
    assert book(reception_api, guest, single, check_in_date="2026-10-05", count=1).status_code == 201


def test_ending_soon_days_must_be_a_number(manager_api):
    res = manager_api.get("/api/v1/reports/ending_soon", {"days": "abc"})
    assert res.status_code == 400 and res.json()["code"] == "validation_error"


class TestPatchWithoutVersion:
    """BIZ-13: partial updates without ``version`` were a 500."""

    def test_room_type_and_room(self, manager_api, single, rooms):
        res = manager_api.patch(f"/api/v1/room-types/{single.pk}", {"name": "مفردة جديدة"}, format="json")
        assert res.status_code == 400 and "version" in res.json()["errors"]
        res = manager_api.patch(f"/api/v1/rooms/{rooms['101'].pk}", {"note": "إطلالة"}, format="json")
        assert res.status_code == 400 and "version" in res.json()["errors"]

    def test_backup_settings_and_alert_rule(self, manager_api):
        from apps.followups.models import AlertRule
        from apps.followups.services import ensure_default_rules

        res = manager_api.patch("/api/v1/backup/settings", {"keep_count": 5}, format="json")
        assert res.status_code == 400 and "version" in res.json()["errors"]
        ensure_default_rules()
        rule = AlertRule.objects.first()
        res = manager_api.patch(f"/api/v1/followups/rules/{rule.pk}", {"name": "قاعدة"}, format="json")
        assert res.status_code == 400 and "version" in res.json()["errors"]
