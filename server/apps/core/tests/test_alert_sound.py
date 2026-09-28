"""The alert sound: built-in tone unless the owner uploads one (owner request 2026-09-28)."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.services import login_with_password
from apps.core import rules
from conftest import PASSWORD

pytestmark = pytest.mark.django_db
URL = "/api/v1/system/alert-sound"
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32


def test_sound_type():
    assert rules.sound_type(b"ID3\x04rest") == "audio/mpeg"
    assert rules.sound_type(b"\xff\xfb\x90\x00") == "audio/mpeg"
    assert rules.sound_type(WAV) == "audio/wav"
    assert rules.sound_type(b"OggS\x00\x02") == "audio/ogg"
    assert rules.sound_type(b"<html>") is None
    assert rules.sound_type(b"\xff") is None


@pytest.fixture
def owner_api(make_user):
    owner = make_user("owner", role="owner", full_name="المالك")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {login_with_password(owner.username, PASSWORD).token}")
    return client


def upload(api, raw, name="bell.wav"):
    return api.post(URL, {"file": SimpleUploadedFile(name, raw)}, format="multipart")


def test_the_owner_chooses_a_sound_and_can_go_back_to_the_default(owner_api, reception_api):
    assert reception_api.get(URL).status_code == 404  # nothing chosen: the built-in tone
    assert reception_api.get("/api/v1/system/settings").json()["alert_sound"] is None

    assert upload(owner_api, WAV).status_code == 204
    res = reception_api.get(URL)
    assert res.status_code == 200 and res["Content-Type"] == "audio/wav" and res.content == WAV
    assert reception_api.get("/api/v1/system/settings").json()["alert_sound"]["name"] == "bell.wav"

    assert owner_api.delete(URL).status_code == 204
    assert reception_api.get(URL).status_code == 404
    assert reception_api.get("/api/v1/system/settings").json()["alert_sound"] is None


def test_only_the_owner_and_only_small_sound_files(owner_api, manager_api):
    assert upload(manager_api, WAV).status_code == 403
    assert manager_api.delete(URL).status_code == 403
    assert upload(owner_api, b"<html>not a sound</html>", "x.mp3").status_code == 400
    assert upload(owner_api, WAV + b"\x00" * rules.ALERT_SOUND_MAX_BYTES).status_code == 400


def test_a_room_may_carry_a_name(manager_api, reception_api, confirm):
    confirm(manager_api)  # prices are a sensitive change
    prices = {"nightly_price": 5_000_000, "weekly_price": 30_000_000, "monthly_price": 90_000_000}
    rt = manager_api.post("/api/v1/room-types/", {"name": "شقة", "capacity": 4, **prices}, format="json")
    assert rt.status_code == 201, rt.json()
    body = {"number": "501", "name": "الشقة العائلية", "floor": 5, "room_type": rt.json()["id"]}
    room = manager_api.post("/api/v1/rooms/", body, format="json")
    assert room.status_code == 201, room.json()
    board = reception_api.get("/api/v1/rooms/board").json()
    row = next(r for r in board["rooms"] if r["number"] == "501")
    assert (row["name"], row["room_type_name"]) == ("الشقة العائلية", "شقة")
    url = f"/api/v1/rooms/{room.json()['id']}"
    res = manager_api.patch(url, {"version": room.json()["version"], "name": ""}, format="json")
    assert res.status_code == 200 and res.json()["name"] == ""
