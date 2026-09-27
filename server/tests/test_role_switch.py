"""An owner config.json over a reception database (the installer's question answered wrongly)."""

import json
import uuid

import pytest
from django.conf import settings
from django.test import override_settings
from rest_framework.test import APIClient

from config import runtime


@pytest.mark.django_db
def test_login_works_on_an_owner_config_when_the_database_already_has_a_hotel(manager, monkeypatch):
    import dataclasses

    monkeypatch.setattr(settings, "RUNTIME", dataclasses.replace(settings.RUNTIME, hotel_id=None))
    with override_settings(SKYTOWERS_ROLE="owner"):
        res = APIClient().post(
            "/api/v1/auth/password", {"username": "manager", "password": "correct-horse"}, format="json"
        )
    assert res.status_code == 200, res.content


@pytest.mark.django_db
def test_writing_without_any_hotel_is_a_clear_409(monkeypatch):
    import dataclasses

    from apps.accounts.models import User

    User.objects.all().delete()
    monkeypatch.setattr(settings, "RUNTIME", dataclasses.replace(settings.RUNTIME, hotel_id=None))
    with override_settings(SKYTOWERS_ROLE="owner"):
        res = APIClient().post("/api/v1/auth/password", {"username": "nobody", "password": "x"}, format="json")
    assert res.status_code in (401, 409) and res.json()["code"] in ("authentication_failed", "no_hotel")


def test_init_force_switches_the_role_and_keeps_the_databases_hotel(tmp_path):
    import sqlite3

    assert runtime.init_config(tmp_path, "owner") is True
    assert runtime.init_config(tmp_path, "reception") is False  # kept: the normal installer path
    hotel = uuid.uuid4()
    (tmp_path / "data").mkdir()
    con = sqlite3.connect(tmp_path / "data" / "hotel.db")
    con.execute("create table accounts_user (id text, hotel_id char(32), created_at text)")
    con.execute("insert into accounts_user values ('u1', ?, '2026-09-01')", (hotel.hex,))
    con.commit()
    con.close()
    assert runtime.init_config(tmp_path, "reception", force=True) is True
    raw = json.loads((tmp_path / "config.json").read_text())
    assert raw == {"role": "reception", "hotel_id": str(hotel)}
    assert runtime.init_config(tmp_path, "owner", force=True) is True
    assert json.loads((tmp_path / "config.json").read_text())["hotel_id"] == str(hotel)  # the owner keeps it too
