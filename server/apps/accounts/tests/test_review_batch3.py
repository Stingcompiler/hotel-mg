"""Review 2026-09-28, batch 3: sign-in paths and the default PIN (SEC-2, SEC-3, OpenAPI schema)."""

from importlib import import_module

import pytest
from django.apps import apps as django_apps
from rest_framework.test import APIClient

from apps.accounts import services
from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_no_django_admin_or_swagger_in_the_installed_app(api):
    """SEC-2: the admin's own login skipped the 5-attempt lockout; both exist in development only."""
    assert api.get("/admin/").status_code == 404
    assert api.get("/admin/login/").status_code == 404
    assert api.get("/api/v1/schema/swagger/").status_code == 404


def test_a_django_session_does_not_authenticate_the_api(manager):
    client = APIClient()
    client.force_login(manager)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_the_default_pin_is_flagged_until_changed(db):
    owner = services.ensure_default_owner()  # a new install: admin / 123456
    assert owner.default_pin is True
    manager = User.objects.create_user("manager", "المدير", role="manager", password="x" * 8, pin="482913")
    assert manager.default_pin is False
    services.reset_pin(owner, manager.pk, "123456")
    manager.refresh_from_db()
    assert manager.default_pin is True
    services.reset_pin(owner, owner.pk, "482913")
    owner.refresh_from_db()
    assert owner.default_pin is False
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {services.login_with_password('manager', 'x' * 8).token}")
    assert client.get("/api/v1/auth/me").json()["default_pin"] is True


def test_existing_accounts_with_the_default_pin_are_flagged_on_upgrade(make_user):
    old = make_user("old.admin", role="owner", full_name="مالك قديم")  # PIN 123456 (conftest PIN)
    other = User.objects.create_user("sara", "سارة", pin="4829")
    User.objects.update(default_pin=False)  # as before the migration
    import_module("apps.accounts.migrations.0004_user_default_pin").flag_default_pins(django_apps, None)
    old.refresh_from_db()
    other.refresh_from_db()
    assert old.default_pin is True and other.default_pin is False
