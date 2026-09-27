"""1.1: backups need no key setup, open on a new PC with the owner's own login, and a new PC adopts a hotel only
when the owner chooses (view only / work on it)."""

import json
from pathlib import Path

import pytest
from django.conf import settings

from apps.accounts import services as accounts
from apps.accounts.models import User
from apps.backup import adopt, keys, keyslots, merge, rules
from apps.backup.models import BackupKeySlot
from service import pending_import

from .support import backup, walk_in

pytestmark = pytest.mark.django_db(transaction=True, databases=["default", "owner", "incoming"])


@pytest.fixture
def hotel_key(hotel):
    keys.ensure_hotel_key()
    return keys.hotel_identity()


def test_a_backup_opens_on_a_new_pc_with_the_managers_own_login(hotel, hotel_key):
    accounts.update_user(hotel, hotel.pk, version=hotel.version, password="manager-pass-1")  # writes the slot
    walk_in(hotel, "201", "محمد عثمان")
    raw = backup(hotel).read_bytes()
    header, _ = rules.unpack(raw)
    assert [s["username"] for s in header["slots"]] == ["manager"]

    # A PC with no key: the file asks for a login, refuses a wrong one, opens with the right one.
    with pytest.raises(merge.ImportRejected) as need:
        merge.open_backup(raw, [])
    assert need.value.checks[-1]["key"] == "credentials_required"
    with pytest.raises(merge.ImportRejected) as wrong:
        merge.open_backup(raw, [], ("manager", "not-it"))
    assert wrong.value.checks[-1]["key"] == "credentials_wrong"
    manifest, files, adopted = merge.open_backup(raw, [], ("Manager", "manager-pass-1"))
    assert manifest["seq"] >= 1 and rules.DB_FILE in files
    assert adopted == str(hotel_key)


def test_slots_follow_passwords_roles_and_the_default_password(hotel, hotel_key):
    owner = accounts.ensure_default_owner() or User.objects.get(username="manager")
    admin = User.objects.filter(username="admin").first()
    if admin:  # the install's default password never gets a slot
        accounts.login_with_password("admin", "123456")
        assert not BackupKeySlot.objects.filter(user=admin).exclude(wrapped="").exists()

    staff = accounts.create_user(
        hotel, username="ahmed", full_name="أحمد", role="reception", pin="2468", password="x-1"
    )
    assert not BackupKeySlot.objects.filter(user=staff).exists()  # staff cannot open backups

    # An account from before 1.1 gets its slot at its first password sign-in.
    assert not BackupKeySlot.objects.filter(user=hotel).exists()
    assert accounts.login_with_password("manager", "pw-123456").ok
    assert [s["username"] for s in keyslots.for_export()] == ["manager"]

    # Deactivated: its slot no longer travels.
    hotel.refresh_from_db()
    other = accounts.create_user(
        hotel, username="mgr2", full_name="مدير ٢", role="manager", pin="1357", password="m2-pass"
    )
    assert {s["username"] for s in keyslots.for_export()} == {"manager", "mgr2"}
    other.refresh_from_db()
    accounts.update_user(hotel, other.pk, version=other.version, is_active=False)
    assert [s["username"] for s in keyslots.for_export()] == ["manager"]
    assert owner is not None


def test_the_file_format_round_trips_and_old_files_still_read():
    raw = rules.pack({"format": 2, "slots": [{"username": "Owner", "wrapped": "w"}]}, b"age-payload")
    header, payload = rules.unpack(raw)
    assert payload == b"age-payload" and rules.slot_for(header, " owner ") == "w"
    assert rules.slot_for(header, "someone") is None and rules.slot_for(None, "owner") is None
    assert rules.unpack(b"age-encryption.org/v1 legacy") == (None, b"age-encryption.org/v1 legacy")
    assert rules.unpack(rules.FORMAT2_MAGIC + b"no newline")[0] is None
    assert rules.unpack(rules.FORMAT2_MAGIC + b"{not json\npayload")[0] is None
    assert rules.unpack(rules.FORMAT2_MAGIC + b"[1]\npayload")[0] is None


def test_adopting_is_offered_only_on_a_new_pc(hotel):
    from rest_framework.test import APIClient

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {accounts.login_with_password('manager', 'pw-123456').token}")
    assert client.get("/api/v1/system/status").json()["can_adopt"] is False
    upload = _upload(backup(hotel))
    res = client.post("/api/v1/backup/adopt", {"file": upload, "mode": "view"}, format="multipart")
    assert res.status_code == 409 and res.json()["code"] == "adopt_not_fresh"


@pytest.mark.parametrize("mode", ["view", "work"])
def test_prepare_leaves_the_hotel_ready_for_the_restart(hotel, hotel_key, monkeypatch, tmp_path, mode):
    accounts.update_user(hotel, hotel.pk, version=hotel.version, password="manager-pass-1")
    walk_in(hotel, "201", "محمد عثمان")
    raw = backup(hotel).read_bytes()
    # The new PC: its own home, no key, nothing but the default account.
    monkeypatch.setattr(settings, "RUNTIME", __import__("dataclasses").replace(settings.RUNTIME, home=tmp_path / "new"))
    monkeypatch.setattr(adopt, "is_fresh", lambda: True)
    restarts = []
    monkeypatch.setattr(adopt, "schedule_restart", lambda: restarts.append(1))

    with pytest.raises(Exception) as need:
        adopt.prepare(raw, "b.age", None, mode)
    assert getattr(need.value, "error_code", "") == "credentials_required"

    assert adopt.prepare(raw, "b.age", ("manager", "manager-pass-1"), mode) == {"mode": mode, "restarting": True}
    pending = pending_import.pending_dir(settings.RUNTIME.home)
    plan = json.loads((pending / "plan.json").read_text(encoding="utf-8"))
    assert plan["mode"] == mode and plan["hotel_id"].startswith("5a7e0000") and restarts == [1]
    assert (pending / ("hotel.db" if mode == "work" else "backup.age")).exists()
    assert str(keys.hotel_identity()) == str(hotel_key)  # the hotel's key is kept for later imports


@pytest.mark.parametrize("mode", ["view", "work"])
def test_the_restart_swaps_files_and_role_and_keeps_the_empty_install(tmp_path, mode):
    home = tmp_path
    (home / "data" / "attachments").mkdir(parents=True)
    (home / "data" / "hotel.db").write_bytes(b"empty install")
    (home / "config.json").write_text(json.dumps({"role": "reception", "hotel_id": "new-pc"}), encoding="utf-8")
    pending = pending_import.pending_dir(home)
    pending.mkdir()
    (pending / "hotel.db").write_bytes(b"the hotel")
    (pending / "attachments" / "guests").mkdir(parents=True)
    (pending / "attachments" / "guests" / "g.jpg").write_bytes(b"id")
    plan = {"mode": mode, "hotel_id": "5a7e0000-0000-4000-8000-000000000001", "file_name": "b.age", "seq": 3}
    (pending / "plan.json").write_text(json.dumps(plan), encoding="utf-8")

    assert pending_import.apply(home) == mode
    config = json.loads((home / "config.json").read_text(encoding="utf-8"))
    [kept] = (home / "backups").glob("pre-import-*")
    assert (kept / "hotel.db").read_bytes() == b"empty install"
    if mode == "work":
        assert config == {"role": "reception", "hotel_id": plan["hotel_id"]}
        assert (home / "data" / "hotel.db").read_bytes() == b"the hotel"
        assert (home / "data" / "attachments" / "guests" / "g.jpg").exists()
    else:
        assert config == {"role": "owner", "hotel_id": ""}
        assert not (home / "data" / "hotel.db").exists()
    assert pending_import.apply(home) is None  # applied once
    assert pending_import.apply(tmp_path / "elsewhere") is None


def test_finish_merges_the_view_copy_then_cleans_up(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "RUNTIME", __import__("dataclasses").replace(settings.RUNTIME, home=tmp_path))
    pending = pending_import.pending_dir(tmp_path)
    pending.mkdir()
    (pending / "backup.age").write_bytes(b"raw")
    (pending / "plan.json").write_text(
        json.dumps({"mode": "view", "applied": True, "file_name": "b.age", "hotel_id": "h"})
    )

    class Run:
        status, error = "failed", "x"

    monkeypatch.setattr(merge, "import_backup", lambda *a, **k: type("R", (), {"run": Run})())
    adopt.finish_pending()
    assert pending.exists()  # a failed merge keeps the folder for support
    Run.status = "ok"
    adopt.finish_pending()
    assert not pending.exists()
    adopt.finish_pending()  # nothing pending: no-op


def _upload(path: Path):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(path.name, path.read_bytes())
