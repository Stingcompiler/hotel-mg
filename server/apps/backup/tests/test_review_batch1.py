"""Review 2026-09-28, batch 1: backups, keys and recovery (BAK-1 … BAK-8)."""

import dataclasses
import io
import zipfile
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.test import override_settings

from apps.accounts import services as accounts
from apps.accounts.models import User
from apps.backup import adopt, export, keys, keyslots, merge, rules
from apps.core.errors import ApiError

from .support import backup, walk_in

pytestmark = pytest.mark.django_db(transaction=True, databases=["default", "owner", "incoming"])


def test_an_unreadable_key_is_moved_aside_and_never_breaks_an_import(hotel):
    """BAK-2: a key another account wrapped (or a damaged file) must not make every import fail."""
    path = keys.hotel_identity_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a key")
    assert keys.hotel_identity() is None and keys.local_identities() == []
    assert not path.exists() and list(path.parent.glob("hotel.age-identity.unreadable-*"))


def test_the_owner_pc_never_makes_a_hotel_key_and_says_why_it_cannot_back_up(hotel):
    cfg = export.backup_settings()
    cfg.owner_recipient = ""
    cfg.save()
    with override_settings(SKYTOWERS_ROLE="owner"):
        run = export.run_backup(hotel)
    assert run.status == "failed" and "مفتاح" in run.message
    assert not keys.hotel_identity_path().exists()


def test_every_backup_carries_every_attachment_and_leaves_no_partial_file(hotel):
    """BAK-4: the newest file alone restores every ID scan; BAK-6: nothing half-written stays behind."""
    root = settings.RUNTIME.attachments_dir
    (root / "guests").mkdir(parents=True, exist_ok=True)
    (root / "guests" / "a.jpg").write_bytes(b"old scan")
    backup(hotel)
    (root / "guests" / "b.jpg").write_bytes(b"new scan")
    walk_in(hotel, "201", "نزيل")
    path = backup(hotel)
    _, files = merge._open(path.read_bytes(), keys.hotel_identity())
    assert {"attachments/guests/a.jpg", "attachments/guests/b.jpg"} <= set(files)
    assert not list(path.parent.glob("*.part"))


def test_leftovers_of_a_backup_cut_short_are_cleaned_at_start(hotel):
    stale = settings.RUNTIME.home / "tmp" / "tmpabc"
    stale.mkdir(parents=True)
    (stale / "hotel.db").write_bytes(b"copy")
    settings.RUNTIME.backups_dir.mkdir(parents=True, exist_ok=True)
    part = settings.RUNTIME.backups_dir / "skytowers-5a7e0000-000009-20260928-0100.age.part"
    part.write_bytes(b"half")
    export.clean_leftovers()
    assert not stale.exists() and not part.exists()


def test_a_backup_says_whether_it_opens_elsewhere(hotel, api):
    """BAK-1: 0 slots = this file opens only on this PC; the status tells the system bar."""
    keys.ensure_hotel_key()
    run = export.run_backup(hotel)
    assert run.status == "ok" and run.slots == 0
    assert api.get("/api/v1/system/status").json()["backup_opens_elsewhere"] is False
    with pytest.raises(merge.ImportRejected) as rejected:
        merge.open_backup(Path(run.path).read_bytes(), [], ("manager", "anything"))
    assert "كلمة المرور الافتراضية" in str(rejected.value)

    accounts.update_user(hotel, hotel.pk, version=hotel.version, password="manager-pass-1")
    assert export.run_backup(hotel).slots == 1
    assert api.get("/api/v1/system/status").json()["backup_opens_elsewhere"] is True


def test_the_owner_who_forgot_the_password_gets_a_new_one_and_backups_follow(hotel):
    """BAK-8: `manage reset_password` unlocks the account and rewrites its key slot."""
    keys.ensure_hotel_key()
    hotel.locked_until = hotel.created_at
    hotel.save(update_fields=["locked_until"])
    call_command("reset_password", "manager", password="brand-new-1", stdout=io.StringIO())
    user = User.objects.get(username="manager")
    assert user.check_password("brand-new-1") and user.locked_until is None
    [slot] = keyslots.for_export()
    assert keyslots.unwrap(slot["wrapped"], "brand-new-1") == str(keys.hotel_identity())
    with pytest.raises(Exception, match="8"):
        call_command("reset_password", "manager", password="123", stdout=io.StringIO())


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("attachments/guests/a.jpg", ("guests", "a.jpg")),
        ("attachments/../../evil.exe", None),
        ("attachments/guests/../../x", None),
        ("attachments/C:/x", None),
        ("attachments/a\\..\\b", None),
        ("attachments/", None),
        ("hotel.db", None),
    ],
)
def test_attachment_names_cannot_leave_the_folder(name, expected):
    assert rules.attachment_path(name) == expected


def test_a_crafted_file_is_refused_not_a_server_error(hotel, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "RUNTIME", dataclasses.replace(settings.RUNTIME, home=tmp_path / "new"))
    monkeypatch.setattr(adopt, "is_fresh", lambda: True)
    monkeypatch.setattr(adopt, "schedule_restart", lambda: None)
    crafted = rules.pack({"format": 2, "slots": [{"username": "manager", "wrapped": 12345}]}, b"payload")
    with pytest.raises(ApiError) as rejected:
        adopt.prepare(crafted, "x.age", ("manager", "pw"), "view")
    assert rejected.value.error_code in ("credentials_wrong", "backup_rejected")

    identity = keys.generate(tmp_path / "k")
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("manifest.json", "{not json")
    import pyrage

    raw = pyrage.encrypt(zip_buf.getvalue(), [keys.recipient(identity)])
    monkeypatch.setattr(keys, "local_identities", lambda: [keys.load(tmp_path / "k")])
    with pytest.raises(ApiError) as broken:
        adopt.prepare(raw, "x.age", None, "view")
    assert broken.value.error_code == "backup_rejected"
