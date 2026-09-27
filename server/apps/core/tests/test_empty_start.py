import dataclasses
import json
import sys

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError

from config import runtime


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A PC's data folder with a database, an attachment and a backup file."""
    monkeypatch.setattr(settings, "RUNTIME", dataclasses.replace(settings.RUNTIME, home=tmp_path))
    settings.RUNTIME.data_dir.mkdir(parents=True)
    settings.RUNTIME.db_path.write_bytes(b"")
    (settings.RUNTIME.attachments_dir / "ids").mkdir(parents=True)
    (settings.RUNTIME.attachments_dir / "ids" / "a.jpg").write_bytes(b"x")
    settings.RUNTIME.backups_dir.mkdir()
    (settings.RUNTIME.backups_dir / "skytowers-5a7e0000-000001-20260926-1828.age").write_bytes(b"x")
    return tmp_path


@pytest.mark.django_db(transaction=True)
def test_reset_moves_everything_aside_and_keeps_the_config(home):
    (home / "config.json").write_text(json.dumps({"role": "reception", "hotel_id": "h-1"}), encoding="utf-8")
    call_command("reset_data", "--yes")
    [kept] = (home / "backups").glob("pre-reset-*")
    assert (kept / "hotel.db").exists() and (kept / "attachments" / "ids" / "a.jpg").exists()
    assert (kept / "skytowers-5a7e0000-000001-20260926-1828.age").exists()
    assert not list((home / "backups").glob("*.age"))
    assert not (home / "data" / "attachments").exists()
    assert json.loads((home / "config.json").read_text(encoding="utf-8"))["hotel_id"] == "h-1"


@pytest.mark.django_db(transaction=True)
def test_reset_on_the_owner_pc_forgets_the_hotel(home, monkeypatch):
    monkeypatch.setattr(settings, "RUNTIME", dataclasses.replace(settings.RUNTIME, role="owner"))
    (home / "config.json").write_text(json.dumps({"role": "owner", "hotel_id": "h-1"}), encoding="utf-8")
    call_command("reset_data", "--yes")
    assert json.loads((home / "config.json").read_text(encoding="utf-8")) == {"role": "owner", "hotel_id": ""}


@pytest.mark.django_db
def test_reset_asks_first(home, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "n")
    with pytest.raises(CommandError):
        call_command("reset_data")
    assert settings.RUNTIME.db_path.exists()


@pytest.mark.django_db
def test_seed_demo_refuses_the_installed_folder(monkeypatch):
    monkeypatch.setattr(runtime, "installed_home", lambda: settings.RUNTIME.home)
    with pytest.raises(CommandError, match="installed program"):
        call_command("seed_demo", "--allow-non-debug")


@pytest.mark.django_db
def test_seed_demo_refuses_a_hotel_with_real_users(make_user):
    make_user("hotel.manager", role="manager", full_name="مدير الفندق")
    with pytest.raises(CommandError, match="real users"):
        call_command("seed_demo", "--allow-non-debug")


def test_only_the_installed_program_defaults_to_program_data(monkeypatch, tmp_path):
    monkeypatch.delenv("SKYTOWERS_HOME", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("ProgramData", str(tmp_path))
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert runtime.default_home().name == ".devdata"  # a source checkout on Windows
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert runtime.default_home() == tmp_path / "SkyTowers"
    assert runtime.is_installed_home(tmp_path / "SkyTowers")
    monkeypatch.setenv("SKYTOWERS_HOME", str(tmp_path / "test"))
    assert runtime.default_home() == tmp_path / "test"


def test_no_installed_folder_off_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    assert runtime.installed_home() is None and not runtime.is_installed_home(tmp_path)
