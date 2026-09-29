"""Review 2026-09-29, batch 12: «حفظ على فلاشة» (E-16)."""

from pathlib import Path

import pytest
from rest_framework.test import APIClient

from apps.accounts.services import login_with_password
from apps.audit.models import AuditLog
from apps.backup import export, usb
from apps.core.errors import ApiError

from .support import backup, do_import, walk_in

pytestmark = pytest.mark.django_db(transaction=True, databases=["default", "owner", "incoming"])


def test_saving_on_a_usb_stick(hotel, tmp_path, monkeypatch):
    stick = tmp_path / "stick"
    stick.mkdir()
    drives = [{"drive": str(stick), "label": "KINGSTON", "free": 10**9}]
    with pytest.raises(ApiError):  # no backup yet
        usb.copy_latest(str(stick), drives)
    export.run_backup(hotel)
    walk_in(hotel, "201", "محمد عثمان")
    newest = export.run_backup(hotel)
    assert newest.status == "ok", newest.message

    copied = usb.copy_latest(str(stick), drives)
    assert [p.name for p in copied] == [Path(newest.path).name]  # every backup holds everything
    assert copied[0].parent == stick / "SkyTowers" and copied[0].stat().st_size == Path(newest.path).stat().st_size
    assert not list((stick / "SkyTowers").glob("*.part"))

    with pytest.raises(ApiError):  # a drive that is not plugged in
        usb.copy_latest("Z:\\", drives)
    with pytest.raises(ApiError):  # not enough room
        usb.copy_latest(str(stick), [{**drives[0], "free": 10}])

    monkeypatch.setattr(usb, "removable_drives", lambda: drives)
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Token {login_with_password('manager', 'pw-123456').token}")
    assert api.get("/api/v1/backup/usb").json() == drives
    res = api.post("/api/v1/backup/usb/copy", {"drive": str(stick)}, format="json")
    assert res.status_code == 200, res.json()
    assert res.json()["folder"].endswith("SkyTowers") and res.json()["files"] == [Path(newest.path).name]
    assert AuditLog.objects.filter(action="backup.usb").exists()


def test_two_reception_pcs_are_flagged_on_the_owner_pc(hotel, owner_identity, monkeypatch):
    """E-17: backups from two reception PCs in the same two weeks mean two separate copies of the hotel."""
    import dataclasses
    from datetime import UTC, datetime, timedelta

    from django.conf import settings

    from apps.backup import rules

    at = datetime(2026, 9, 29, tzinfo=UTC)
    assert not rules.two_devices("", None, "PC-2", at)
    assert not rules.two_devices("PC-1", at, "PC-1", at)
    assert rules.two_devices("PC-1", at - timedelta(days=3), "PC-2", at)
    assert not rules.two_devices("PC-1", at - timedelta(days=30), "PC-2", at)  # a move, long ago

    first = do_import(backup(hotel), owner_identity[0])
    assert first.run.status == "ok" and first.run.device == settings.RUNTIME.device_name
    assert not [c for c in first.run.checks if c["key"] == "device"]
    monkeypatch.setattr(settings, "RUNTIME", dataclasses.replace(settings.RUNTIME, device_name="RECEPTION-2"))
    walk_in(hotel, "202", "أحمد علي")
    second = do_import(backup(hotel), owner_identity[0])
    assert second.run.status == "ok"  # a warning, not a refusal
    warning = next(c for c in second.run.checks if c["key"] == "device")
    assert warning["status"] == "warn" and "RECEPTION-2" in warning["detail"]
