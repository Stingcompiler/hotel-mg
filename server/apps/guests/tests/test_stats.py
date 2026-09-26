import pytest

pytestmark = pytest.mark.django_db


def test_guest_list_carries_history_numbers_and_filters(api_as_manager):
    debtors = api_as_manager.get("/api/v1/guests/", {"debt": 1}).json()["results"]
    assert sorted(g["last_stay"]["room"] for g in debtors) == ["203", "305"]
    assert sum(g["debt"] for g in debtors) == 5_700_000
    assert all(g["in_house"] and g["stays_count"] >= 1 for g in debtors)
    in_house = api_as_manager.get("/api/v1/guests/", {"in_house": 1}).json()
    assert in_house["count"] == 18
    everyone = api_as_manager.get("/api/v1/guests/").json()
    assert everyone["count"] >= in_house["count"]

    guest = debtors[0]
    history = api_as_manager.get(f"/api/v1/guests/{guest['id']}/history").json()
    assert history[0]["room"] == guest["last_stay"]["room"] and history[0]["balance"] == guest["debt"]
    assert history[0]["status_label"] == "مسكّن"
