from datetime import timedelta
from pathlib import Path

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.services import login_with_password
from apps.backup import drive
from apps.backup.drive import RemoteFile
from apps.backup.models import DriveUpload
from apps.core.errors import ApiError

from .support import backup, do_import, walk_in

pytestmark = pytest.mark.django_db(transaction=True, databases=["default", "owner", "incoming"])


class FakeDrive(drive.DriveClient):
    def __init__(self):
        self.files: dict[str, tuple[str, bytes]] = {}
        self.offline = False

    def _net(self):
        if self.offline:
            raise ConnectionError("no route to host")

    def account_email(self):
        return "skytowers.backup@gmail.com"

    def upload(self, path: Path) -> str:
        self._net()
        file_id = f"f{len(self.files) + 1}"
        self.files[file_id] = (path.name, path.read_bytes())
        return file_id

    def list_backups(self):
        self._net()
        return [RemoteFile(i, name, len(data), "2026-09-26T14:03:00Z") for i, (name, data) in self.files.items()]

    def download(self, file_id):
        self._net()
        return self.files[file_id][1]


@pytest.fixture
def fake(monkeypatch, hotel):
    client = FakeDrive()
    monkeypatch.setattr(drive, "get_client", lambda: client)
    drive.save_token({"refresh_token": "x", "email": "skytowers.backup@gmail.com"})
    return client


@pytest.fixture
def api(hotel):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {login_with_password('manager', 'pw-123456').token}")
    return client


def test_sync_uploads_pending_backups_once(fake, api, hotel):
    walk_in(hotel, "201", "محمد عثمان")
    backup(hotel)
    backup(hotel)
    status = api.get("/api/v1/backup/drive/status").json()
    assert (status["linked"], status["email"], status["pending_uploads"]) == (True, "skytowers.backup@gmail.com", 2)
    res = api.post("/api/v1/backup/drive/sync").json()
    assert (res["uploaded"], res["message"]) == (2, "رُفعت 2 نسخ")
    assert api.post("/api/v1/backup/drive/sync").json()["message"] == "لا جديد — كل النسخ مرفوعة"
    assert len(fake.files) == 2 and DriveUpload.objects.filter(ok=True).count() == 2
    runs = api.get("/api/v1/backup/runs").json()["results"]
    assert all(r["uploaded"] for r in runs)


def test_offline_is_503_and_retried_later(fake, api, hotel):
    backup(hotel)
    fake.offline = True
    res = api.post("/api/v1/backup/drive/sync")
    assert res.status_code == 503 and res.json()["code"] == "offline"
    failed = DriveUpload.objects.get(ok=False)
    assert failed.message.startswith("لا يوجد اتصال بالإنترنت")
    now = timezone.now()
    assert drive.upload_if_due(now + timedelta(minutes=5)) is None  # waits 10 minutes between attempts
    fake.offline = False
    assert drive.upload_if_due(now + timedelta(minutes=11)) == 1


def test_owner_downloads_newer_backups_and_imports_from_drive(fake, hotel, owner_identity, monkeypatch):
    walk_in(hotel, "201", "محمد عثمان")
    first = backup(hotel)
    walk_in(hotel, "202", "فاطمة أحمد")
    backup(hotel)
    drive.upload_pending(client=fake)

    monkeypatch.setattr("apps.backup.merge.last_imported", lambda target="default": None)
    fetched = drive.download_new(fake)
    assert sorted(fetched) == sorted(name for name, _ in fake.files.values())
    assert drive.download_new(fake) == []  # already in incoming/

    name, raw = drive.fetch_one("f2", fake)
    result = do_import(Path(drive.incoming_dir() / name), owner_identity[0])
    assert result.run.status == "ok"
    assert first.name in {p.name for p in drive.incoming_dir().iterdir()}
    with pytest.raises(ApiError):
        drive.fetch_one("nope", fake)


def test_candidates_and_owner_sync_endpoint(fake, api, hotel):
    backup(hotel)
    drive.upload_pending(client=fake)
    with override_settings(SKYTOWERS_ROLE="owner"):
        res = api.post("/api/v1/owner/drive/sync").json()
        assert len(res["downloaded"]) == 1 and res["message"] == "نُزّلت 1 نسخ جديدة"
        candidates = api.get("/api/v1/owner/import/candidates").json()
        assert [(c["seq"], c["state"], c["local"], c["drive_file_id"]) for c in candidates] == [(1, "new", True, "f1")]


def test_unlink_and_not_linked(fake, api, monkeypatch):
    assert api.post("/api/v1/backup/drive/unlink").json()["linked"] is False
    monkeypatch.undo()  # real get_client again
    with pytest.raises(ApiError) as exc:
        drive.get_client()
    assert exc.value.error_code == "drive_not_linked"


def test_no_drive_upload_alert(fake, hotel):
    from apps.followups import engine
    from apps.followups.models import FollowupTask

    backup(hotel)
    now = timezone.now()
    engine.tick(now + timedelta(hours=1))
    assert not FollowupTask.objects.filter(rule__trigger_kind="no_drive_upload").exists()
    engine.tick(now + timedelta(hours=73))
    assert FollowupTask.objects.filter(rule__trigger_kind="no_drive_upload").count() == 1
