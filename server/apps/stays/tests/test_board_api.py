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
