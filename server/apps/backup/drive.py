"""Google Drive transport for backup files (spec §9.2).

Reception: upload every successful backup that is not on Drive yet to «SkyTowers/backups».
Owner: list backups on Drive newer than the last import and download them to ``incoming/``.
No internet → 503 ``offline``; nothing else in the app depends on connectivity.

Credentials: ``client_secret.json`` is placed in SKYTOWERS_HOME at install time (never in the repo);
the refresh token is stored in ``SKYTOWERS_HOME/drive/token.bin`` (DPAPI-wrapped on Windows).
All network calls go through a ``DriveClient`` so tests use an in-memory fake.
"""

import json
import socket
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.errors import ApiError

from . import keys, rules
from .models import BackupRun, DriveUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER_PATH = ("SkyTowers", "backups")
RETRY_EVERY = timedelta(minutes=10)


@dataclass(frozen=True)
class RemoteFile:
    id: str
    name: str
    size: int
    created_at: str

    @property
    def parsed(self):
        return rules.parse_file_name(self.name)


class DriveClient:
    """What the rest of the app needs from Drive. The real one wraps googleapiclient."""

    def account_email(self) -> str: ...

    def upload(self, path: Path) -> str: ...

    def list_backups(self) -> list[RemoteFile]: ...

    def download(self, file_id: str) -> bytes: ...


# --- Stored credentials ------------------------------------------------------------------------


def _drive_dir() -> Path:
    return settings.RUNTIME.home / "drive"


def client_secret_path() -> Path:
    return settings.RUNTIME.home / "client_secret.json"


def _token_path() -> Path:
    return _drive_dir() / "token.bin"


def save_token(info: dict) -> None:
    _drive_dir().mkdir(parents=True, exist_ok=True)
    _token_path().write_bytes(keys.protect(json.dumps(info).encode("utf-8")))


def load_token() -> dict | None:
    if not _token_path().exists():
        return None
    return json.loads(keys.unprotect(_token_path().read_bytes()).decode("utf-8"))


def unlink_account() -> None:
    _token_path().unlink(missing_ok=True)


def is_linked() -> bool:
    return _token_path().exists()


# --- Real client -----------------------------------------------------------------------------------


class GoogleDriveClient(DriveClient):  # pragma: no cover - exercised against real Drive on the hotel PC
    def __init__(self, token: dict):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        self.creds = Credentials.from_authorized_user_info(token, SCOPES)
        self.service = build("drive", "v3", credentials=self.creds, cache_discovery=False)
        self._folder = None

    def account_email(self) -> str:
        return self.service.about().get(fields="user(emailAddress)").execute()["user"]["emailAddress"]

    def _folder_id(self) -> str:
        if self._folder:
            return self._folder
        parent = "root"
        for name in FOLDER_PATH:
            q = (
                f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and '{parent}' in parents "
                "and trashed = false"
            )
            found = self.service.files().list(q=q, fields="files(id)").execute().get("files", [])
            if found:
                parent = found[0]["id"]
            else:
                body = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent]}
                parent = self.service.files().create(body=body, fields="id").execute()["id"]
        self._folder = parent
        return parent

    def upload(self, path: Path) -> str:
        from googleapiclient.http import MediaFileUpload

        media = MediaFileUpload(str(path), mimetype="application/octet-stream", resumable=True)
        body = {"name": path.name, "parents": [self._folder_id()]}
        return self.service.files().create(body=body, media_body=media, fields="id").execute()["id"]

    def list_backups(self) -> list[RemoteFile]:
        q = f"'{self._folder_id()}' in parents and trashed = false and name contains 'skytowers-'"
        files = self.service.files().list(q=q, fields="files(id,name,size,createdTime)", pageSize=200).execute()
        return [RemoteFile(f["id"], f["name"], int(f.get("size", 0)), f["createdTime"]) for f in files.get("files", [])]

    def download(self, file_id: str) -> bytes:
        return self.service.files().get_media(fileId=file_id).execute()


def get_client() -> DriveClient:
    """Replaced in tests. Raises ``drive_not_linked`` when no account is linked."""
    token = load_token()
    if token is None:
        raise ApiError("drive_not_linked", 409)
    return GoogleDriveClient(token)


OFFLINE_ERRORS: tuple[type[BaseException], ...] = (socket.gaierror, TimeoutError, ConnectionError)


def _offline(exc: BaseException) -> bool:
    try:
        from google.auth.exceptions import TransportError
        from httplib2.error import ServerNotFoundError
    except ImportError:  # pragma: no cover
        return isinstance(exc, OFFLINE_ERRORS)
    return isinstance(exc, (*OFFLINE_ERRORS, TransportError, ServerNotFoundError))


# --- OAuth (manager links the account) -----------------------------------------------------------------


def _redirect_uri(prefix: str) -> str:
    return f"http://127.0.0.1:8471/api/v1/{prefix}/drive/callback"


def auth_url(prefix: str) -> str:  # pragma: no cover - needs client_secret.json and Google
    from google_auth_oauthlib.flow import Flow

    if not client_secret_path().exists():
        raise ApiError("drive_not_configured", 409)
    flow = Flow.from_client_secrets_file(
        str(client_secret_path()), scopes=SCOPES, redirect_uri=_redirect_uri(prefix), autogenerate_code_verifier=True
    )
    url, state = flow.authorization_url(access_type="offline", prompt="consent")
    _drive_dir().mkdir(parents=True, exist_ok=True)
    (_drive_dir() / "pending.json").write_text(json.dumps({"state": state, "verifier": flow.code_verifier}))
    return url


def finish_auth(prefix: str, code: str, state: str) -> str:  # pragma: no cover - needs Google
    from google_auth_oauthlib.flow import Flow

    pending = json.loads((_drive_dir() / "pending.json").read_text())
    if pending["state"] != state:
        raise ApiError("permission_denied", 403)
    flow = Flow.from_client_secrets_file(
        str(client_secret_path()),
        scopes=SCOPES,
        redirect_uri=_redirect_uri(prefix),
        state=state,
        code_verifier=pending["verifier"],
    )
    flow.fetch_token(code=code)
    save_token(json.loads(flow.credentials.to_json()))
    (_drive_dir() / "pending.json").unlink(missing_ok=True)
    return GoogleDriveClient(load_token()).account_email()


# --- Reception: upload -------------------------------------------------------------------------------


def pending_runs():
    return BackupRun.objects.filter(status=BackupRun.Status.OK).exclude(uploads__ok=True).order_by("seq")


def upload_pending(actor=None, client: DriveClient | None = None) -> int:
    """Upload every backup not on Drive yet, oldest first. Offline → 503; failures are recorded per run."""
    client = client or get_client()
    uploaded = 0
    for run in pending_runs():
        path = Path(run.path)
        if not path.exists():
            continue  # removed by retention before it could be uploaded
        try:
            file_id = client.upload(path)
        except Exception as exc:  # noqa: BLE001 - recorded, then offline is reported to the caller
            with transaction.atomic():
                DriveUpload.objects.create(run=run, ok=False, message=_message(exc), created_by=actor)
            if _offline(exc):
                raise ApiError("offline", 503, uploaded=uploaded) from None
            raise ApiError("drive_error", 502, detail=_message(exc)) from None
        with transaction.atomic():
            DriveUpload.objects.create(run=run, ok=True, drive_file_id=file_id, created_by=actor)
        uploaded += 1
    return uploaded


def _message(exc: BaseException) -> str:
    if _offline(exc):
        return "لا يوجد اتصال بالإنترنت — النسخ المحلية محفوظة وسيُعاد الرفع تلقائيًا"
    return f"خطأ من Drive: {exc}"[:300]


def upload_if_due(now=None) -> int | None:
    """Scheduler: after a backup, retry pending uploads at most every 10 minutes, silently when offline."""
    from .export import backup_settings

    now = now or timezone.now()
    if not is_linked() or not backup_settings().auto_drive or not pending_runs().exists():
        return None
    last = DriveUpload.objects.order_by("-created_at").first()
    if last and now - last.created_at < RETRY_EVERY:
        return None
    try:
        return upload_pending()
    except ApiError:
        return 0


def last_upload_at():
    last = DriveUpload.objects.filter(ok=True).order_by("-created_at").first()
    return last.created_at if last else None


# --- Owner: download ----------------------------------------------------------------------------------


def _hotel8() -> str | None:
    return str(settings.RUNTIME.hotel_id).replace("-", "")[:8] if settings.RUNTIME.hotel_id else None


def remote_backups(client: DriveClient) -> list[RemoteFile]:
    """This hotel's backups on Drive, newest first (any hotel before the first import)."""
    try:
        files = client.list_backups()
    except Exception as exc:  # noqa: BLE001
        if _offline(exc):
            raise ApiError("offline", 503) from None
        raise ApiError("drive_error", 502, detail=_message(exc)) from None
    hotel8 = _hotel8()
    mine = [f for f in files if f.parsed and (hotel8 is None or f.parsed[0] == hotel8)]
    return sorted(mine, key=lambda f: f.parsed[1], reverse=True)


def incoming_dir() -> Path:
    return settings.RUNTIME.home / "incoming"


def download_new(client: DriveClient | None = None) -> list[str]:
    """Owner «مزامنة مع Drive»: fetch files newer than the last import into ``incoming/``."""
    from .merge import last_imported

    client = client or get_client()
    last = last_imported()
    newest_imported = last.backup_seq if last and last.backup_seq else 0
    fetched = []
    incoming_dir().mkdir(parents=True, exist_ok=True)
    for remote in remote_backups(client):
        if remote.parsed[1] <= newest_imported or (incoming_dir() / remote.name).exists():
            continue
        try:
            data = client.download(remote.id)
        except Exception as exc:  # noqa: BLE001
            if _offline(exc):
                raise ApiError("offline", 503, downloaded=fetched) from None
            raise ApiError("drive_error", 502, detail=_message(exc)) from None
        (incoming_dir() / remote.name).write_bytes(data)
        fetched.append(remote.name)
    return fetched


def fetch_one(file_id: str, client: DriveClient | None = None) -> tuple[str, bytes]:
    """Download a specific Drive file (import dialog «من Drive»)."""
    client = client or get_client()
    remote = next((f for f in remote_backups(client) if f.id == file_id), None)
    if remote is None:
        raise ApiError("not_found", 404)
    local = incoming_dir() / remote.name
    if local.exists():
        return remote.name, local.read_bytes()
    try:
        data = client.download(file_id)
    except Exception as exc:  # noqa: BLE001
        if _offline(exc):
            raise ApiError("offline", 503) from None
        raise
    incoming_dir().mkdir(parents=True, exist_ok=True)
    local.write_bytes(data)
    return remote.name, data
