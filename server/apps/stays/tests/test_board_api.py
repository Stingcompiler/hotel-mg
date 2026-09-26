import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def test_typed_board_endpoint_matches_the_view_param(api_as_manager):
    board = api_as_manager.get("/api/v1/rooms/board").json()
    assert board == api_as_manager.get("/api/v1/rooms/", {"view": "board"}).json()
    assert board["summary"]["occupied"] == 18 and len(board["rooms"]) == 30
    room_305 = next(r for r in board["rooms"] if r["number"] == "305")
    assert room_305["display_status"] == "overdue"
    assert room_305["stay"]["balance"] == 4_200_000
    assert room_305["stay"]["duration_label"] in {"يومي", "أسبوعي", "شهري", "مختلط"}
    assert "guest_phone" in room_305["stay"]
    assert room_305["manual_targets"] == []
    cleaning = next(r for r in board["rooms"] if r["status"] == "cleaning")
    assert cleaning["manual_targets"] == ["maintenance", "ready"]


def test_board_needs_sign_in(api):
    call_command("seed_demo", "--allow-non-debug")
    assert api.get("/api/v1/rooms/board").status_code == 401


def test_stay_detail_carries_guest_room_days_left_and_log(api_as_manager):
    board = api_as_manager.get("/api/v1/rooms/board").json()
    room_305 = next(r for r in board["rooms"] if r["number"] == "305")
    detail = api_as_manager.get(f"/api/v1/stays/{room_305['stay']['id']}").json()
    assert detail["room"]["number"] == "305" and detail["room"]["display_status"] == "overdue"
    assert detail["days_left"] == room_305["stay"]["days_left"] < 0
    assert detail["guest"]["full_name"] == room_305["stay"]["guest_name"]
    labels = [e["label"] for e in detail["log"]]
    assert "إنشاء الحجز" in labels and "قيد إقامة" in labels
    assert detail["log"] == sorted(detail["log"], key=lambda e: e["at"], reverse=True)
