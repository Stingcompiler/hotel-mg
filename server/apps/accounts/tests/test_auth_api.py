from datetime import timedelta

import pytest
import time_machine
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import LoginEvent
from apps.audit.models import AuditLog
from apps.core.clock import is_clock_blocked, observe_clock
from conftest import PASSWORD, PIN

pytestmark = pytest.mark.django_db


def pin_login(api, user, pin):
    return api.post("/api/v1/auth/pin", {"user_id": str(user.pk), "pin": pin}, format="json")


def test_login_screen_lists_active_users_only(api, reception, make_user):
    make_user("khalid.m", full_name="خالد (سابق)", is_active=False)
    res = api.get("/api/v1/auth/users")
    assert res.status_code == 200
    assert [u["full_name"] for u in res.json()] == ["أحمد علي"]
    assert set(res.json()[0]) == {"id", "full_name", "role"}


def test_pin_login_returns_token_and_records_it(api, reception):
    res = pin_login(api, reception, PIN)
    assert res.status_code == 200
    body = res.json()
    assert body["token"] and body["user"]["username"] == "ahmed.ali"
    assert LoginEvent.objects.filter(user=reception, kind="pin").count() == 1
    assert AuditLog.objects.filter(action="auth.login_pin", actor=reception).exists()

    api.credentials(HTTP_AUTHORIZATION=f"Token {body['token']}")
    assert api.get("/api/v1/auth/me").json()["full_name"] == "أحمد علي"


def test_wrong_pin_counts_down_then_locks(api, reception):
    for left in (4, 3, 2, 1):
        res = pin_login(api, reception, "000000")
        assert res.status_code == 401
        assert res.json()["code"] == "authentication_failed"
        assert res.json()["attempts_left"] == left

    res = pin_login(api, reception, "000000")
    assert res.status_code == 423
    assert res.json()["code"] == "account_locked"
    assert "locked_until" in res.json()
    assert AuditLog.objects.filter(action="auth.locked").count() == 1
    assert LoginEvent.objects.filter(user=reception, kind="failed").count() == 5

    # Even the right PIN is refused while locked; it works again after five minutes.
    assert pin_login(api, reception, PIN).status_code == 423
    with time_machine.travel(timezone.now() + timedelta(minutes=5, seconds=1)):
        assert pin_login(api, reception, PIN).status_code == 200


def test_successful_login_resets_failed_attempts(api, reception):
    pin_login(api, reception, "000000")
    pin_login(api, reception, PIN)
    reception.refresh_from_db()
    assert reception.failed_attempts == 0


def test_unknown_or_inactive_user_gets_generic_error(api, make_user):
    ghost = make_user("khalid.m", is_active=False)
    res = pin_login(api, ghost, PIN)
    assert res.status_code == 401
    assert "attempts_left" not in res.json()
    res = api.post("/api/v1/auth/password", {"username": "nobody", "password": "x"}, format="json")
    assert res.status_code == 401


def test_password_login(api, manager):
    res = api.post("/api/v1/auth/password", {"username": "manager", "password": PASSWORD}, format="json")
    assert res.status_code == 200
    assert LoginEvent.objects.filter(user=manager, kind="password").exists()


def test_token_expires_after_twelve_hours(api, reception):
    token = pin_login(api, reception, PIN).json()["token"]
    api.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    with time_machine.travel(timezone.now() + timedelta(hours=12, minutes=1)):
        res = api.get("/api/v1/auth/me")
    assert res.status_code == 401
    assert res.json()["code"] == "token_expired"


def test_new_login_replaces_previous_token(api, reception):
    first = pin_login(api, reception, PIN).json()["token"]
    pin_login(api, reception, PIN)
    api.credentials(HTTP_AUTHORIZATION=f"Token {first}")
    assert api.get("/api/v1/auth/me").status_code == 401


def test_logout_revokes_token(reception_api):
    assert reception_api.post("/api/v1/auth/logout").status_code == 204
    assert reception_api.get("/api/v1/auth/me").status_code == 401


class TestConfirmation:
    def test_wrong_password_is_refused(self, manager_api):
        res = manager_api.post("/api/v1/auth/confirm", {"password": "wrong"}, format="json")
        assert res.status_code == 401
        assert res.json()["attempts_left"] == 4

    def test_sensitive_action_needs_fresh_token(self, manager_api, confirm):
        payload = {"username": "salma.h", "full_name": "سلمى حسن", "role": "reception", "pin": "4321"}
        res = manager_api.post("/api/v1/users/", payload, format="json")
        assert res.status_code == 403
        assert res.json()["code"] == "confirmation_required"

        confirm(manager_api)
        assert manager_api.post("/api/v1/users/", payload, format="json").status_code == 201

        with time_machine.travel(timezone.now() + timedelta(minutes=5, seconds=1)):
            payload["username"] = "other"
            assert manager_api.post("/api/v1/users/", payload, format="json").status_code == 403

    def test_token_is_bound_to_its_user(self, manager_api, confirm, make_user):
        confirm(manager_api)
        stolen = manager_api._credentials["HTTP_X_CONFIRM_TOKEN"]
        other = make_user("boss2", role="manager", full_name="مدير 2")
        client = APIClient()
        token = client.post("/api/v1/auth/password", {"username": "boss2", "password": PASSWORD}, format="json")
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.json()['token']}", HTTP_X_CONFIRM_TOKEN=stolen)
        res = client.patch(f"/api/v1/users/{other.pk}", {"version": other.version, "full_name": "x"}, format="json")
        assert res.status_code == 403


class TestUserManagement:
    def test_reception_cannot_manage_users(self, reception_api):
        assert reception_api.get("/api/v1/users/").status_code == 403

    def test_manager_lists_users(self, manager_api, reception):
        names = {u["username"] for u in manager_api.get("/api/v1/users/").json()}
        assert names == {"manager", "ahmed.ali"}

    def test_create_user_validates_input(self, manager_api, confirm, reception):
        confirm(manager_api)
        res = manager_api.post(
            "/api/v1/users/",
            {"username": "ahmed.ali", "full_name": "x", "role": "manager", "pin": "12"},
            format="json",
        )
        assert res.status_code == 400
        assert set(res.json()["errors"]) == {"username", "pin"}
        res = manager_api.post(
            "/api/v1/users/", {"username": "new.mgr", "full_name": "x", "role": "manager", "pin": "1234"}, format="json"
        )
        assert res.json()["errors"] == {"password": ["كلمة المرور مطلوبة للمدير والمالك."]}

    def test_manager_cannot_create_owner(self, manager_api, confirm):
        confirm(manager_api)
        res = manager_api.post(
            "/api/v1/users/",
            {"username": "own", "full_name": "المالك", "role": "owner", "pin": "1234", "password": "long-password"},
            format="json",
        )
        assert res.status_code == 403

    def test_update_checks_version_and_audits(self, manager_api, confirm, reception):
        confirm(manager_api)
        url = f"/api/v1/users/{reception.pk}"
        res = manager_api.patch(url, {"version": reception.version + 5, "full_name": "x"}, format="json")
        assert res.status_code == 409
        assert res.json()["code"] == "version_conflict"

        res = manager_api.patch(url, {"version": reception.version, "full_name": "أحمد علي محمد"}, format="json")
        assert res.status_code == 200
        assert res.json()["full_name"] == "أحمد علي محمد"
        row = AuditLog.objects.get(action="user.update")
        assert row.before["full_name"] == "أحمد علي" and row.after["full_name"] == "أحمد علي محمد"

    def test_deactivation_revokes_session(self, manager_api, confirm, reception, reception_api):
        confirm(manager_api)
        reception.refresh_from_db()
        res = manager_api.patch(
            f"/api/v1/users/{reception.pk}", {"version": reception.version, "is_active": False}, format="json"
        )
        assert res.status_code == 200
        assert reception_api.get("/api/v1/auth/me").status_code == 401

    def test_cannot_deactivate_self(self, manager_api, confirm, manager):
        confirm(manager_api)
        manager.refresh_from_db()
        res = manager_api.patch(f"/api/v1/users/{manager.pk}", {"version": manager.version, "is_active": False},
                                format="json")  # fmt: skip
        assert res.status_code == 403

    def test_reset_pin_and_unlock(self, manager_api, confirm, api, reception):
        for _ in range(5):
            pin_login(api, reception, "000000")
        assert pin_login(api, reception, PIN).status_code == 423

        assert manager_api.post(f"/api/v1/users/{reception.pk}/unlock").status_code == 200
        assert pin_login(api, reception, PIN).status_code == 200

        confirm(manager_api)
        res = manager_api.post(f"/api/v1/users/{reception.pk}/reset-pin", {"pin": "7777"}, format="json")
        assert res.status_code == 200
        assert pin_login(api, reception, "7777").status_code == 200
        assert AuditLog.objects.filter(action__in=["user.unlock", "user.reset_pin"]).count() == 2


def test_manager_approves_clock_rollback(manager_api, confirm, reception_api):
    now = timezone.now()
    observe_clock(now + timedelta(hours=1))  # last seen in the "future": the real now looks like a rollback
    res = reception_api.post("/api/v1/users/", {}, format="json")  # any non-exempt write
    assert res.status_code == 423
    assert AuditLog.objects.filter(action="system.clock_rollback").exists()

    assert reception_api.post("/api/v1/system/clock/approve").status_code == 403  # manager only
    assert manager_api.post("/api/v1/system/clock/approve").json()["code"] == "confirmation_required"
    confirm(manager_api)
    assert manager_api.post("/api/v1/system/clock/approve").status_code == 204
    assert not is_clock_blocked()
    assert AuditLog.objects.filter(action="system.clock_approve").exists()
