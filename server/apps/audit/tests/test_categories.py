import pytest
from rest_framework.test import APIClient

from apps.accounts.services import login_with_password
from apps.audit import rules
from apps.core.seed import demo_data

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("action", "after", "expected"),
    [
        ("guest.view_document", None, "sensitive"),
        ("stay.checkout", {"override_by": "u1"}, "override"),
        ("stay.cancel", {"approved_by": "u1"}, "override"),
        ("stay.check_in", {"override_reason": "سعر خاص"}, "override"),
        ("stay.check_in", {"override_reason": ""}, "stay"),
        ("payment.reverse", None, "reversal"),
        ("folio.reversal", {}, "reversal"),
        ("payment.refund", None, "reversal"),
        ("auth.login_pin", None, "login"),
        ("payment.payment", None, "payment"),
        ("folio.service", None, "payment"),
        ("reservation.create", None, "stay"),
        ("room.set_status", None, "settings"),
        ("followup.rule_update", None, "settings"),
        ("shift.open", ["not", "a", "dict"], "other"),
    ],
)
def test_category(action, after, expected):
    assert rules.category(action, after) == expected
    assert rules.CATEGORIES[expected]


def test_audit_list_filters_and_labels(api_as_manager):
    rows = api_as_manager.get("/api/v1/audit/", {"category": "payment"}).json()["results"]
    assert rows and {r["category"] for r in rows} == {"payment"} and rows[0]["category_label"] == "دفعة"
    by_name = api_as_manager.get("/api/v1/audit/", {"q": "المدير"}).json()["results"]
    assert by_name and {r["actor_name"] for r in by_name} == {"المدير"}
    long_ago = {"date_from": "2000-01-01", "date_to": "2000-01-02"}
    assert api_as_manager.get("/api/v1/audit/", long_ago).json()["count"] == 0
    assert api_as_manager.get("/api/v1/audit/", {"category": "nope"}).status_code == 400
    assert api_as_manager.get("/api/v1/audit/", {"date_from": "yesterday"}).status_code == 400


def test_audit_log_export_is_manager_only_and_hidden_from_the_index(api_as_manager):
    res = api_as_manager.get("/api/v1/reports/audit_log/export", {"format": "csv", "category": "stay"})
    assert res.status_code == 200 and "سجل التدقيق" not in res.content.decode("utf-8-sig").splitlines()[0]
    report = api_as_manager.get("/api/v1/reports/audit_log", {"category": "stay"}).json()
    assert report["rows"] and {r["category"] for r in report["rows"]} == {"إقامة"}
    assert api_as_manager.get("/api/v1/reports/audit_log", {"category": "x"}).status_code == 400
    assert "audit_log" not in {r["name"] for r in api_as_manager.get("/api/v1/reports/").json()}
    reception = APIClient()
    token = login_with_password("ahmed.ali", demo_data.DEMO_PASSWORD).token
    reception.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    assert reception.get("/api/v1/reports/audit_log").status_code == 403


def test_action_labels():
    assert rules.action_label("stay.check_in") == "تسكين"
    assert rules.action_label("payment.deposit") == "عربون"
    assert rules.action_label("something.new") == "something.new"


def test_summary_lists_changed_fields_before_and_after():
    assert rules.summary({"days_before": 3, "version": 1}, {"days_before": 5, "version": 2}) == "التنبيه الأول: 3 ← 5"
    assert rules.summary(None, {"number": "101", "in_service": True}) == "الرقم: 101 · في الخدمة: نعم"
    assert rules.summary({"note": ""}, {"note": "x", "extra": {"a": 1}}) == "ملاحظة: — ← x"
    assert rules.summary(None, None) == ""


def test_action_label_falls_back_to_the_key():
    assert rules.action_label("user.create") == "إنشاء مستخدم"
    assert rules.action_label("unknown.thing") == "unknown.thing"


def test_summary_formats_money_and_hides_ids_and_times():
    after = {
        "amount": 750000,
        "shift": "4055d471-b0d9-4cf8-ad08-01c17e644af6",
        "opened_at": "2026-09-26T18:23:27Z",
        "closed_by": None,
        "counted": 1234567,
    }
    assert rules.summary(None, after) == "المبلغ: 7,500 ج.س · المعدود: 12,345.67 ج.س"
    assert rules.summary({"amount": 100}, {"amount": -250}) == "المبلغ: 1 ج.س ← -2.50 ج.س"


def test_summary_uses_arabic_values_and_hides_internal_flags():
    before = {"role": "reception", "is_staff": False}
    after = {"role": "manager", "is_staff": True}
    assert rules.summary(before, after) == "الدور: موظف استقبال ← مدير"
