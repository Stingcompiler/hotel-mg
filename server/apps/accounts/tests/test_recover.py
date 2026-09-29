"""«نسيت كلمة المرور؟» offline: the account's reference email confirms who asks (owner decision 2026-09-28)."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import login_with_password
from apps.audit.models import AuditLog
from conftest import PASSWORD

pytestmark = pytest.mark.django_db
URL = "/api/v1/auth/recover"


@pytest.fixture
def owner(make_user):
    return make_user("owner", role="owner", full_name="المالك", email="owner@hotel.sd")


def test_the_right_email_sets_a_new_password_and_signs_other_sessions_out(api, owner):
    old = APIClient()
    old.credentials(HTTP_AUTHORIZATION=f"Token {login_with_password('owner', PASSWORD).token}")
    body = {"username": "owner", "email": " Owner@Hotel.SD ", "password": "new-secret-1"}
    assert api.post(URL, body, format="json").status_code == 204
    assert old.get("/api/v1/auth/me").status_code == 401
    login = {"username": "owner", "password": "new-secret-1"}
    assert api.post("/api/v1/auth/password", login, format="json").status_code == 200
    assert AuditLog.objects.filter(action="user.recover_password").exists()


def test_a_wrong_email_counts_as_a_failed_sign_in(api, owner):
    body = {"username": "owner", "email": "someone@else.sd", "password": "new-secret-1"}
    res = api.post(URL, body, format="json")
    assert res.status_code == 401 and res.json()["attempts_left"] == 4
    for _ in range(4):
        res = api.post(URL, body, format="json")
    assert res.status_code == 423 and res.json()["code"] == "account_locked"
    good = {**body, "email": "owner@hotel.sd"}
    assert api.post(URL, good, format="json").status_code == 423  # locked: the right email waits too


def test_no_email_or_no_user_gives_nothing_away(api, make_user):
    make_user("sara", full_name="سارة")  # no email saved
    for username in ("sara", "nobody"):
        body = {"username": username, "email": "x@y.sd", "password": "new-secret-1"}
        res = api.post(URL, body, format="json")
        assert res.status_code == 401 and res.json()["code"] == "authentication_failed"
    short = {"username": "sara", "email": "x@y.sd", "password": "123"}
    assert api.post(URL, short, format="json").status_code == 400


def test_email_is_set_when_creating_or_editing_a_user(manager_api, confirm):
    confirm(manager_api)
    body = {"username": "ali", "full_name": "علي", "role": "reception", "pin": "4829", "email": "Ali@Hotel.sd"}
    res = manager_api.post("/api/v1/users/", body, format="json")
    assert res.status_code == 201, res.json()
    assert res.json()["email"] == "ali@hotel.sd"
    user = User.objects.get(username="ali")
    url = f"/api/v1/users/{user.pk}"
    res = manager_api.patch(url, {"version": user.version, "email": "new@hotel.sd"}, format="json")
    assert res.status_code == 200 and res.json()["email"] == "new@hotel.sd"
    assert manager_api.patch(url, {"version": user.version + 1, "email": "bad"}, format="json").status_code == 400
