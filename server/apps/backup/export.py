"""Encrypted backup files (spec §9.1).

VACUUM INTO → hotel.db copy; attachments (all weekly, else changed since the last full); manifest with
SHA-256 per file; zip; age-encrypt to the hotel key (and a pre-1.1 owner key); a plain header carries the key
slots (keyslots.py); write to the backups folder and the second folder;
apply retention. Backups are device records (``BackupRun``), not audit entries, so a backup does not
count as a "change" for the next one.
"""

import io
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pyrage
from django.conf import settings
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.billing.services import next_number
from apps.core.hotel import current_hotel_id
from apps.core.models import SCHEMA_VERSION

from . import keys, keyslots, rules
from .models import BackupRun, BackupSettings


def backup_settings() -> BackupSettings:
    obj, _ = BackupSettings.objects.get_or_create(hotel_id=current_hotel_id())
    return obj


def _snapshot_database(target: Path) -> None:
    """Consistent copy of the live SQLite database (must run outside a transaction)."""
    if connection.vendor != "sqlite":  # pragma: no cover - PostgreSQL would use pg_dump here
        raise NotImplementedError("backup export supports SQLite only")
    with connection.cursor() as cursor:
        cursor.execute("VACUUM INTO %s", [str(target)])


def _attachments(since: datetime | None) -> dict[str, bytes]:
    root = settings.RUNTIME.attachments_dir
    files = {}
    if not root.exists():
        return files
    for path in sorted(root.rglob("*")):
        if path.is_file() and (since is None or datetime.fromtimestamp(path.stat().st_mtime, tz=UTC) > since):
            files[f"attachments/{path.relative_to(root).as_posix()}"] = path.read_bytes()
    return files


def _last_ok(**filters) -> BackupRun | None:
    return BackupRun.objects.filter(status=BackupRun.Status.OK, **filters).order_by("-created_at").first()


def _retention(folder: Path, keep: int, keep_days: int, hotel8: str) -> list[str]:
    backups = []
    for path in folder.glob("skytowers-*.age"):
        parsed = rules.parse_file_name(path.name)
        if parsed and parsed[0] == hotel8:
            backups.append((parsed[1], path))
    newest_first = [str(p) for _, p in sorted(backups, reverse=True)]
    stamped = [(p, datetime.fromtimestamp(Path(p).stat().st_mtime, tz=UTC)) for p in newest_first]
    removed = sorted(set(rules.to_delete(newest_first, keep)) | set(rules.too_old(stamped, keep_days, timezone.now())))
    for path in removed:
        Path(path).unlink(missing_ok=True)
    return removed


def _record(kind: str, status: str, actor=None, **fields) -> BackupRun:
    with transaction.atomic():
        return BackupRun.objects.create(kind=kind, status=status, created_by=actor, **fields)


def run_backup(actor=None, kind: str = BackupRun.Kind.MANUAL, now: datetime | None = None) -> BackupRun:
    now = now or timezone.now()
    config = backup_settings()
    audit_seq = AuditLog.objects.order_by("-seq").values_list("seq", flat=True).first() or 0
    last = _last_ok()
    if kind != BackupRun.Kind.MANUAL and last and last.audit_seq == audit_seq:
        return _record(kind, BackupRun.Status.SKIPPED, actor, audit_seq=audit_seq, message="لا تغييرات منذ آخر نسخة")

    last_full = _last_ok(full=True)
    full = rules.needs_full(last_full.created_at if last_full else None, now)
    tmp_root = settings.RUNTIME.home / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=tmp_root) as tmp:
        try:
            db_copy = Path(tmp) / rules.DB_FILE
            _snapshot_database(db_copy)
            files = {rules.DB_FILE: db_copy.read_bytes(), **_attachments(None if full else last_full.created_at)}
            migrations = [f"{app}.{name}" for app, name in MigrationRecorder(connection).applied_migrations()]
            with transaction.atomic():
                seq = next_number("backup")
                hotel_id = current_hotel_id()
                manifest = rules.build_manifest(
                    hotel_id=hotel_id,
                    seq=seq,
                    created_at=now,
                    schema_version=SCHEMA_VERSION,
                    app_version=settings.APP_VERSION,
                    migrations=migrations,
                    full=full,
                    audit_seq=audit_seq,
                    files=files,
                )
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr(rules.MANIFEST, rules.manifest_bytes(manifest))
                    for name, data in files.items():
                        zf.writestr(name, data)
                # 1.1: always to the hotel key (made here on first use), plus a pre-1.1 owner key when one is set,
                # so owner PCs installed earlier keep opening new backups.
                recipients = [keys.recipient(keys.ensure_hotel_key())]
                if config.owner_recipient:
                    recipients.append(keys.recipient(config.owner_recipient))
                header = {
                    "format": 2,
                    "hotel_id": str(hotel_id),
                    "seq": seq,
                    "created_at": manifest["created_at"],
                    "slots": keyslots.for_export(),
                }
                encrypted = rules.pack(header, pyrage.encrypt(buf.getvalue(), recipients))
                name = rules.file_name(str(hotel_id), seq, timezone.localtime(now))
                folder = settings.RUNTIME.backups_dir
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / name
                target.write_bytes(encrypted)
                second_path, second_error = "", ""
                if config.second_dir:
                    try:
                        Path(config.second_dir).mkdir(parents=True, exist_ok=True)
                        second_path = str(Path(config.second_dir) / name)
                        shutil.copyfile(target, second_path)
                    except OSError as exc:  # e.g. USB disk not connected: the main copy still counts
                        second_path, second_error = "", f"المجلد الثاني غير متاح: {exc.strerror or exc}"[:300]
                run = BackupRun.objects.create(
                    kind=kind,
                    status=BackupRun.Status.OK,
                    seq=seq,
                    full=full,
                    path=str(target),
                    second_path=second_path,
                    second_error=second_error,
                    size=len(encrypted),
                    sha256=rules.sha256_hex(encrypted),
                    audit_seq=audit_seq,
                    created_by=actor,
                )
        except Exception as exc:  # noqa: BLE001 - any failure becomes a visible failed run
            return _record(kind, BackupRun.Status.FAILED, actor, message=str(exc)[:300])

    hotel8 = str(current_hotel_id()).replace("-", "")[:8]
    _retention(settings.RUNTIME.backups_dir, config.keep_count, config.keep_days, hotel8)
    if config.second_dir and Path(config.second_dir).exists():
        _retention(Path(config.second_dir), config.keep_count, config.keep_days, hotel8)
    return run


def run_if_due(now: datetime | None = None) -> BackupRun | None:
    """Called by the scheduler every minute: a scheduled backup every ``interval_hours``."""
    now = now or timezone.now()
    config = backup_settings()
    last = BackupRun.objects.filter(kind=BackupRun.Kind.SCHEDULED).order_by("-created_at").first()
    last_any = _last_ok()
    anchor = max(
        filter(None, [last.created_at if last else None, last_any.created_at if last_any else None]), default=None
    )
    if rules.is_due(anchor, config.interval_hours, now):
        return run_backup(kind=BackupRun.Kind.SCHEDULED, now=now)
    return None


def last_backup_at() -> datetime | None:
    last = _last_ok()
    return last.created_at if last else None
