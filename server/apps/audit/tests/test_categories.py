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
