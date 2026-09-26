import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User

pytestmark = pytest.mark.django_db

BODY = {"full_name": "مدير الفندق", "username": "boss", "password": "secret-123", "pin": "4321"}


def test_first_run_creates_the_manager_and_signs_in():
    api = APIClient()
    assert api.get("/api/v1/system/status").json()["needs_setup"] is True
    res = api.post("/api/v1/auth/setup", BODY, format="json")
    assert res.status_code == 200
    assert res.json()["user"]["role"] == "manager"
    user = User.objects.get(username="boss")
    assert user.check_pin("4321") and user.check_password("secret-123")
    assert api.get("/api/v1/system/status").json()["needs_setup"] is False
    api.credentials(HTTP_AUTHORIZATION=f"Token {res.json()['token']}")
    assert api.get("/api/v1/auth/me").json()["username"] == "boss"


def test_setup_only_once():
    api = APIClient()
    assert api.post("/api/v1/auth/setup", BODY, format="json").status_code == 200
    again = api.post("/api/v1/auth/setup", {**BODY, "username": "other"}, format="json")
    assert again.status_code == 409
    assert again.json()["code"] == "setup_done"
    assert not User.objects.filter(username="other").exists()


def test_setup_validates_pin_and_password():
    res = APIClient().post("/api/v1/auth/setup", {**BODY, "pin": "12", "password": "x"}, format="json")
    assert res.status_code == 400
    assert set(res.json()["errors"]) == {"pin", "password"}


def test_owner_pc_cannot_create_users_by_setup():
    with override_settings(SKYTOWERS_ROLE="owner"):
        res = APIClient().post("/api/v1/auth/setup", BODY, format="json")
    assert res.status_code == 403
