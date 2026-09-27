"""A new install opens on the login page with the default owner account (owner decision 2026-09-27)."""

import pytest
from django.core.management import call_command

from apps.accounts import rules, services
from apps.accounts.models import Role, User

pytestmark = pytest.mark.django_db


def _status(api):
    return api.get("/api/v1/system/status").json()


def test_first_start_creates_the_owner_account_once(api):
    user = services.ensure_default_owner()
    assert user.username == "admin" and user.role == Role.OWNER and user.default_password
    assert user.check_password("123456") and user.check_pin("123456")
    assert services.ensure_default_owner() is None
    assert User.objects.count() == 1
    body = _status(api)
    assert body["needs_setup"] is False
    assert body["default_login"] == {"username": "admin", "password": "123456", "pin": "123456"}


def test_no_default_account_when_the_hotel_has_users(make_user):
    make_user("hotel.manager", role="manager", full_name="مدير الفندق")
    assert services.ensure_default_owner() is None
    assert not User.objects.filter(username=rules.DEFAULT_USERNAME).exists()


def test_the_owner_signs_in_and_the_hint_goes_once_the_password_changes(api):
    services.ensure_default_owner()
    res = api.post("/api/v1/auth/password", {"username": "admin", "password": "123456"}, format="json")
    assert res.status_code == 200, res.json()
    api.credentials(HTTP_AUTHORIZATION=f"Token {res.json()['token']}")
    me = api.get("/api/v1/auth/me").json()
    assert me["role"] == "owner" and me["default_password"] is True

    owner = User.objects.get(username="admin")
    services.update_user(owner, owner.pk, version=owner.version, password="a-new-password")
    assert api.get("/api/v1/auth/me").json()["default_password"] is False
    assert _status(api)["default_login"] is None


def test_the_owner_creates_and_edits_staff_logins(api):
    owner = services.ensure_default_owner()
    staff = services.create_user(owner, username="ahmed", full_name="أحمد", role="reception", pin="2468", password=None)
    services.update_user(owner, staff.pk, version=staff.version, username="ahmed.ali", password="staff-pass-1")
    staff.refresh_from_db()
    assert staff.username == "ahmed.ali" and staff.check_password("staff-pass-1")
    manager = services.create_user(owner, username="mgr", full_name="مدير", role="manager", pin="1357")
    assert manager.role == Role.MANAGER


def test_seed_demo_still_runs_beside_the_untouched_default_account():
    services.ensure_default_owner()
    call_command("seed_demo", "--allow-non-debug")
    assert User.objects.filter(username="manager").exists()


def test_a_login_cannot_be_renamed_to_a_taken_username():
    from apps.core.errors import ApiError

    owner = services.ensure_default_owner()
    staff = services.create_user(owner, username="ahmed", full_name="أحمد", role="reception", pin="2468")
    with pytest.raises(ApiError) as e:
        services.update_user(owner, staff.pk, version=staff.version, username="admin")
    assert e.value.error_code == "username_taken"
