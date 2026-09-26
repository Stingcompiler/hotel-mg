import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.audit.models import AuditLog
from apps.cash.models import Expense, Shift

pytestmark = pytest.mark.django_db


def open_shift(api, opening=5_000_000):
    res = api.post("/api/v1/shifts/open", {"opening": opening}, format="json")
    assert res.status_code == 201, res.json()
    return res.json()


def expense(api, amount=500_000, method="cash", **extra):
    payload = {"category": "supplies", "amount": amount, "note": "مواد تنظيف", "method": method, **extra}
    return api.post("/api/v1/expenses/", payload, format="json")


class TestShift:
    def test_no_shift_blocks_cash_operations(self, reception_api):
        current = reception_api.get("/api/v1/shifts/current").json()
        assert current["shift"] is None and current["movements"] == []
        res = expense(reception_api)
        assert res.status_code == 409 and res.json()["code"] == "no_open_shift"

    def test_one_open_shift_per_device(self, reception_api, manager_api):
        open_shift(reception_api)
        res = manager_api.post("/api/v1/shifts/open", {"opening": 0}, format="json")
        assert res.status_code == 409 and res.json()["code"] == "shift_already_open"

    def test_close_with_difference_needs_reason(self, reception_api, reception):
        open_shift(reception_api)
        expense(reception_api, 750_000)
        expense(reception_api, 500_000)
        expense(reception_api, 3_800_000, method="bankak")  # not from the drawer
        current = reception_api.get("/api/v1/shifts/current").json()
        assert current["totals"]["expenses"]["cash"] == 1_250_000
        assert current["totals"]["expected"] == 3_750_000
        assert [m["kind"] for m in current["movements"]][-1] == "open"

        res = reception_api.post("/api/v1/shifts/close", {"counted": 3_500_000}, format="json")
        assert res.status_code == 400
        assert res.json()["code"] == "reason_required" and res.json()["difference"] == -250_000
        res = reception_api.post(
            "/api/v1/shifts/close",
            {"counted": 3_500_000, "difference_reason": "أُعيد 2,500 لنزيل 108 نقدًا"},
            format="json",
        )
        assert res.status_code == 200
        body = res.json()
        assert (body["expected"], body["counted"], body["difference"]) == (3_750_000, 3_500_000, -250_000)
        assert AuditLog.objects.filter(action="shift.close", actor=reception).exists()

        current = reception_api.get("/api/v1/shifts/current").json()
        assert current["shift"] is None and current["last_closed"]["id"] == body["id"]
        assert current["suggested_opening"] == 5_000_000

    def test_history(self, reception_api):
        open_shift(reception_api)
        reception_api.post("/api/v1/shifts/close", {"counted": 5_000_000}, format="json")
        open_shift(reception_api)
        reception_api.post(
            "/api/v1/shifts/close", {"counted": 4_700_000, "difference_reason": "خطأ باقٍ"}, format="json"
        )
        history = reception_api.get("/api/v1/shifts/").json()
        assert (history["count"], history["with_difference"], history["net_difference"]) == (2, 1, -300_000)
        detail = reception_api.get(f"/api/v1/shifts/{history['shifts'][0]['id']}").json()
        assert detail["shift"]["difference_reason"] == "خطأ باقٍ"


class TestExpenses:
    def test_reverse_creates_opposite_row(self, reception_api):
        open_shift(reception_api)
        original = expense(reception_api).json()
        res = reception_api.post(
            f"/api/v1/expenses/{original['id']}/reverse", {"reason": "المبلغ الصحيح 4,500"}, format="json"
        )
        assert res.status_code == 201
        assert res.json()["amount"] == -500_000 and res.json()["reverses"] == original["id"]
        again = reception_api.post(f"/api/v1/expenses/{original['id']}/reverse", {"reason": "x"}, format="json")
        assert again.json()["code"] == "already_reversed"
        assert Expense.objects.count() == 2
        assert reception_api.get("/api/v1/shifts/current").json()["totals"]["expenses"]["cash"] == 0

    def test_attachment_flag_and_upload(self, reception_api):
        open_shift(reception_api)
        big = expense(reception_api, 2_500_000, note="إصلاح تسرب مياه — غرفة 410").json()
        assert big["attachment_missing"] is True
        assert reception_api.get("/api/v1/expenses/summary").json()["awaiting_attachment"] == 1
        buf = io.BytesIO()
        Image.new("RGB", (300, 200), "white").save(buf, "JPEG")
        res = reception_api.post(
            f"/api/v1/expenses/{big['id']}/attachments",
            {"file": SimpleUploadedFile("r.jpg", buf.getvalue())},
            format="multipart",
        )
        assert res.status_code == 201 and res.json()["attachment_missing"] is False
        att = res.json()["attachments"][0]
        img = reception_api.get(f"/api/v1/expenses/{big['id']}/attachments/{att}")
        assert img.status_code == 200 and img["Content-Type"] == "image/jpeg"

    def test_list_scopes_and_summary(self, reception_api):
        open_shift(reception_api)
        expense(reception_api, 500_000)
        expense(reception_api, 750_000, category="purchases")
        assert len(reception_api.get("/api/v1/expenses/", {"scope": "shift"}).json()["results"]) == 2
        only = reception_api.get("/api/v1/expenses/", {"category": "purchases"}).json()["results"]
        assert [e["category_label"] for e in only] == ["مشتريات"]
        summary = reception_api.get("/api/v1/expenses/summary").json()
        assert (summary["shift_total"], summary["shift_count"], summary["top_category"]) == (1_250_000, 2, "purchases")

    def test_amount_must_be_positive_integer(self, reception_api):
        open_shift(reception_api)
        assert expense(reception_api, 0).status_code == 400
        assert expense(reception_api, 12.5).status_code == 400


def test_hotel_settings(reception_api, manager_api):
    assert reception_api.get("/api/v1/system/settings").json()["expense_attachment_threshold"] == 2_000_000
    assert reception_api.patch("/api/v1/system/settings", {"version": 1}, format="json").status_code == 403
    res = manager_api.patch(
        "/api/v1/system/settings",
        {"version": 1, "digits": "arabic", "expense_attachment_threshold": 3_000_000},
        format="json",
    )
    assert res.status_code == 200 and res.json()["digits"] == "arabic"
    assert AuditLog.objects.filter(action="settings.update").exists()
    stale = manager_api.patch("/api/v1/system/settings", {"version": 1, "phone": "1"}, format="json")
    assert stale.status_code == 409


def test_shift_row_is_unique_per_device_at_db_level(reception):
    from django.db import IntegrityError, transaction
    from django.utils import timezone

    Shift.objects.create(device="PC", opened_at=timezone.now(), opening=0)
    with pytest.raises(IntegrityError), transaction.atomic():
        Shift.objects.create(device="PC", opened_at=timezone.now(), opening=0)
