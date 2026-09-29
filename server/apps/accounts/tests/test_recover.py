"""«نسيت كلمة المرور؟» offline (owner decisions 2026-09-28 and 2026-09-29, review C-1…C-7).

The owner proves it with his one-time recovery code; other accounts with a password use the email saved on them.
"""

from datetime import timedelta

import pytest
import time_machine
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import rules, services
from apps.accounts.models import User
from apps.accounts.services import login_with_password
from apps.audit.models import AuditLog
from conftest import PASSWORD

pytestmark = pytest.mark.django_db
URL = "/api/v1/auth/recover"


def test_rules():
    assert rules.format_recovery_code("ABCD2345EFGH") == "ABCD-2345-EFGH"
    assert rules.normalize_recovery_code(" abcd-2345 efgh ") == "ABCD2345EFGH"
    assert rules.normalize_recovery_code("0O1IL") == "QQJJJ"  # look-alikes read as letters of the alphabet
    assert not rules.password_long_enough("1234567") and rules.password_long_enough("12345678")
    now = timezone.now()
    assert rules.recovery_failure(0, 0, now) == (1, 0, None)
    assert rules.recovery_failure(4, 0, now) == (0, 1, now + timedelta(minutes=15))
    assert rules.recovery_failure(4, 1, now) == (0, 2, now + timedelta(hours=1))
    assert rules.recovery_failure(4, 9, now) == (0, 10, now + timedelta(hours=24))  # capped at a day


@pytest.fixture
def owner(make_user):
    return make_user("owner", role="owner", full_name="المالك", email="owner@hotel.sd")


def test_the_owner_recovers_with_the_code_not_the_email(api, owner):
    code = services.new_recovery_code(owner)
    old = APIClient()
    old.credentials(HTTP_AUTHORIZATION=f"Token {login_with_password('owner', PASSWORD).token}")
    by_email = {"username": "owner", "email": "owner@hotel.sd", "password": "new-secret-1"}
    assert api.post(URL, by_email, format="json").status_code == 401  # knowing the email is not enough (C-1)
    body = {"username": "owner", "recovery_code": code.lower().replace("-", " "), "password": "new-secret-1"}
    res = api.post(URL, body, format="json")
    assert res.status_code == 200, res.json()
    new_code = res.json()["recovery_code"]
    assert new_code and new_code != code  # a code works once; a new one is handed out
    assert old.get("/api/v1/auth/me").status_code == 401
    login = {"username": "owner", "password": "new-secret-1"}
    assert api.post("/api/v1/auth/password", login, format="json").status_code == 200
    assert api.post(URL, {**body, "password": "another-1"}, format="json").status_code == 401  # old code spent
    assert AuditLog.objects.filter(action="user.recover_password").exists()


def test_staff_recover_with_their_email(api, make_user):
    make_user("manager", role="manager", full_name="المدير", email="Manager@Hotel.sd")
    body = {"username": "manager", "email": " manager@hotel.SD ", "password": "new-secret-1"}
    res = api.post(URL, body, format="json")
    assert res.status_code == 200 and res.json()["recovery_code"] is None


def test_wrong_attempts_lock_recovery_longer_each_time_but_never_the_sign_in(api, owner):
    services.new_recovery_code(owner)
    body = {"username": "owner", "recovery_code": "AAAA-AAAA-AAAA", "password": "new-secret-1"}
    res = api.post(URL, body, format="json")
    assert res.status_code == 401 and res.json()["attempts_left"] == 4
    for _ in range(4):
        res = api.post(URL, body, format="json")
    assert res.status_code == 423 and res.json()["code"] == "account_locked"
    login = {"username": "owner", "password": PASSWORD}
    assert api.post("/api/v1/auth/password", login, format="json").status_code == 200  # C-4
    owner.refresh_from_db()
    first = owner.recovery_locked_until
    with time_machine.travel(first + timedelta(seconds=1)):
        for _ in range(5):
            res = api.post(URL, body, format="json")
        assert res.status_code == 423
    owner.refresh_from_db()
    assert owner.recovery_locked_until - first > timedelta(minutes=50)  # the second lock is an hour


def test_no_recovery_for_pin_only_accounts_or_unknown_users(api, make_user):
    User.objects.create_user("sara", "سارة", pin="4829", email="sara@hotel.sd")  # no password (C-3)
    for username in ("sara", "nobody"):
        body = {"username": username, "email": "sara@hotel.sd", "password": "new-secret-1"}
        res = api.post(URL, body, format="json")
        assert res.status_code == 401 and res.json()["code"] == "authentication_failed"
    short = {"username": "sara", "email": "sara@hotel.sd", "password": "1234567"}
    assert api.post(URL, short, format="json").status_code == 400  # 8 characters at least (C-6)


def test_recovery_only_takes_json(api, owner):
    """A web page elsewhere cannot post a form to the sign-in endpoints (C-5)."""
    res = api.post(URL, {"username": "owner", "email": "x", "password": "new-secret-1"}, format="multipart")
    assert res.status_code == 415
    res = api.post("/api/v1/auth/password", {"username": "owner", "password": PASSWORD}, format="multipart")
    assert res.status_code == 415


def test_the_owner_gets_a_code_when_setting_the_password_and_can_ask_for_a_new_one(owner, confirm):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {login_with_password('owner', PASSWORD).token}")
    confirm(client)
    me = client.get("/api/v1/auth/me").json()
    assert me["has_recovery_code"] is False and me["recovery_code"] is None
    body = {"version": owner.version, "password": "brand-new-1"}
    res = client.patch(f"/api/v1/users/{owner.pk}", body, format="json")
    assert res.status_code == 200 and len(res.json()["recovery_code"]) == 14  # XXXX-XXXX-XXXX
    assert client.get("/api/v1/auth/me").json()["has_recovery_code"] is True
    res = client.post(f"/api/v1/users/{owner.pk}/recovery-code")
    assert res.status_code == 200 and len(res.json()["recovery_code"]) == 14


def test_a_confirmation_does_not_outlive_its_session(owner, confirm):
    """C-7: the token for sensitive actions was still valid after signing out and in again."""
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {login_with_password('owner', PASSWORD).token}")
    confirm(client)
    token = client._credentials["HTTP_X_CONFIRM_TOKEN"]
    fresh = APIClient()
    fresh.credentials(
        HTTP_AUTHORIZATION=f"Token {login_with_password('owner', PASSWORD).token}", HTTP_X_CONFIRM_TOKEN=token
    )
    res = fresh.post(f"/api/v1/users/{owner.pk}/recovery-code")
    assert res.status_code == 403 and res.json()["code"] == "confirmation_required"


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
    short = manager_api.patch(url, {"version": user.version + 1, "password": "1234567"}, format="json")
    assert short.status_code == 400  # C-6
