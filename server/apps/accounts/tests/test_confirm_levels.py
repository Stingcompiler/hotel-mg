"""Two confirmation levels (owner decision 2026-10-22, decision 237): the PIN confirms day-to-day approvals, the
password everything that guards the accounts and the backups."""

import pytest

from apps.accounts import rules

pytestmark = pytest.mark.django_db

ROOM_TYPE = {"name": "جناح", "nightly_price": 3_000_000, "weekly_price": 18_000_000, "monthly_price": 60_000_000}
NEW_USER = {"username": "salma.h", "full_name": "سلمى حسن", "role": "reception", "pin": "4321"}


def _confirm(client, **body):
    res = client.post("/api/v1/auth/confirm", body, format="json")
    if res.status_code == 200:
        client.credentials(
            HTTP_AUTHORIZATION=client._credentials["HTTP_AUTHORIZATION"],
            HTTP_X_CONFIRM_TOKEN=res.json()["confirm_token"],
        )
    return res


@pytest.fixture
def own_pin(manager):
    manager.set_pin("2468")
    manager.save()
    return "2468"


def test_rule_password_covers_everything_pin_only_day_to_day():
    assert rules.confirmation_enough(rules.CONFIRM_PASSWORD, rules.CONFIRM_PASSWORD)
    assert rules.confirmation_enough(rules.CONFIRM_PASSWORD, rules.CONFIRM_PIN)
    assert rules.confirmation_enough(rules.CONFIRM_PIN, rules.CONFIRM_PIN)
    assert not rules.confirmation_enough(rules.CONFIRM_PIN, rules.CONFIRM_PASSWORD)
    assert not rules.confirmation_enough("", rules.CONFIRM_PIN)


def test_a_pin_confirms_prices_but_not_account_changes(manager_api, own_pin):
    res = _confirm(manager_api, pin=own_pin)
    assert res.status_code == 200 and res.json()["level"] == "pin"
    assert manager_api.post("/api/v1/room-types/", ROOM_TYPE, format="json").status_code == 201

    res = manager_api.post("/api/v1/users/", NEW_USER, format="json")
    assert res.status_code == 403
    assert res.json()["code"] == "password_confirmation_required"


def test_the_password_still_confirms_everything(manager_api, confirm):
    confirm(manager_api)
    assert manager_api.post("/api/v1/users/", NEW_USER, format="json").status_code == 201
    assert manager_api.post("/api/v1/room-types/", ROOM_TYPE, format="json").status_code == 201


def test_the_default_pin_never_confirms(manager_api):
    res = _confirm(manager_api, pin="123456")  # the fixtures' PIN is the well-known default
    assert res.status_code == 403
    assert res.json()["code"] == "default_pin_not_accepted"


def test_a_wrong_pin_counts_against_the_lock(manager_api, own_pin):
    res = _confirm(manager_api, pin="1357")
    assert res.status_code == 401
    assert res.json()["attempts_left"] == 4


def test_an_account_without_pin_and_a_body_with_both_or_neither(manager_api, manager):
    manager.pin_hash = ""
    manager.save()
    assert _confirm(manager_api, pin="2468").json()["code"] == "pin_not_set"
    assert _confirm(manager_api, pin="2468", password="x").status_code == 400
    assert _confirm(manager_api).status_code == 400


def test_an_old_token_without_a_level_counts_as_a_password_one(manager_api, manager):
    from django.core import signing

    from apps.accounts.services import CONFIRM_SALT, _session_tag

    key = manager_api._credentials["HTTP_AUTHORIZATION"].split()[1]
    raw = signing.dumps({"u": str(manager.pk), "s": _session_tag(key)}, salt=CONFIRM_SALT)
    manager_api.credentials(HTTP_AUTHORIZATION=f"Token {key}", HTTP_X_CONFIRM_TOKEN=raw)
    assert manager_api.post("/api/v1/users/", NEW_USER, format="json").status_code == 201
