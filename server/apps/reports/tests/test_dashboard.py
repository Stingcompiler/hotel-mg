from rest_framework.test import APIClient

from apps.accounts.services import login_with_password
from apps.core.seed import demo_data


def _dashboard(api, **params):
    res = api.get("/api/v1/reports/owner-dashboard", params)
    assert res.status_code == 200, res.json()
    return res.json()


def test_kpis_match_the_seeded_board(api_as_manager):
    data = _dashboard(api_as_manager)
    kpis = data["kpis"]
    assert data["period"]["key"] == "month" and data["period"]["label"] == "هذا الشهر"
    assert kpis["occupancy_today"]["occupied"] == 18 and kpis["occupancy_today"]["rooms"] == data["rooms"]
    assert kpis["debts"]["value"] == 5_700_000 and kpis["debts"]["count"] == 2
    assert kpis["debts"]["largest"] == {"room": "305", "amount": 4_200_000}
    assert len(data["occupancy"]["series"]) == 30
    assert data["occupancy"]["series"][-1]["occupied"] == 18
    assert data["overdue_stays"] == 2
    assert sum(w["revenue"] for w in data["weeks"]) == kpis["revenue"]["value"]
    assert sum(w["collected"] for w in data["weeks"]) == kpis["collected"]["value"]


def test_attention_lists_overdue_stays_and_large_debts(api_as_manager):
    attention = _dashboard(api_as_manager)["attention"]
    kinds = [a["kind"] for a in attention]
    assert kinds.count("overdue") == 2
    # Default threshold 50,000: only room 305 (42,000) is below it, so no debt item.
    assert "debt" not in kinds
    url = "/api/v1/system/settings"
    assert api_as_manager.patch(url, {"debt_attention_threshold": 1}, format="json").status_code == 400
    version = api_as_manager.get(url).json()["version"]
    res = api_as_manager.patch(url, {"debt_attention_threshold": 4_000_000, "version": version}, format="json")
    assert res.status_code == 200, res.json()
    debts = [a for a in _dashboard(api_as_manager)["attention"] if a["kind"] == "debt"]
    assert len(debts) == 1 and "305" in debts[0]["text"]


def test_periods(api_as_manager):
    prev = _dashboard(api_as_manager, period="previous")["period"]
    assert prev["label"] == "الشهر السابق" and prev["date_to"] < _dashboard(api_as_manager)["period"]["date_from"]
    ninety = _dashboard(api_as_manager, period="90days")
    assert ninety["period"]["label"] == "آخر 90 يومًا"
    assert api_as_manager.get("/api/v1/reports/owner-dashboard", {"period": "year"}).status_code == 400


def test_reception_cannot_open_the_dashboard(seeded):
    client = APIClient()
    token = login_with_password("ahmed.ali", demo_data.DEMO_PASSWORD).token
    client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    assert client.get("/api/v1/reports/owner-dashboard").status_code == 403


def test_period_average_matches_the_occupancy_report(api_as_manager):
    for period in ("month", "previous", "90days"):
        data = _dashboard(api_as_manager, period=period)
        span = data["period"]
        report = api_as_manager.get(
            "/api/v1/reports/occupancy", {"date_from": span["date_from"], "date_to": span["date_to"]}
        ).json()
        assert data["kpis"]["occupancy_today"]["period_average"] == report["meta"]["totals"]["occupancy"], period


def test_ninety_days_weeks_carry_their_months(api_as_manager):
    weeks = _dashboard(api_as_manager, period="90days")["weeks"]
    assert len(weeks) == 13
    assert all("/" in w["label"] and "الأسبوع" not in w["label"] for w in weeks)
    assert _dashboard(api_as_manager)["weeks"][0]["label"].startswith("الأسبوع 1 (1–")


def test_staff_counts_alerts_that_fell_due_before_the_shift_opened(api_as_manager):
    from apps.followups import engine
    from apps.followups.models import FollowupTask

    engine.tick()
    tasks = FollowupTask.objects.count()
    assert tasks > 0
    staff = _dashboard(api_as_manager, period="90days")["staff"]
    # The seeded shift opened after these alerts fell due: they were waiting for it, not dropped.
    assert sum(s["total"] for s in staff) == tasks
