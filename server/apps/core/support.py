"""«حزمة الدعم»: what a support call needs, written to a USB stick — the service log, versions and the backup and
import history. No database, keys, attachments or config secrets leave the PC."""

import io
import json
import platform
import shutil
import sys
import zipfile
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from apps.core.errors import ApiError

MAX_LOG_BYTES = 10 * 1024 * 1024


def _info() -> dict:
    runtime = settings.RUNTIME
    home = Path(runtime.home)
    db = runtime.db_path
    try:
        free = shutil.disk_usage(home).free
    except OSError:
        free = None
    return {
        "app_version": settings.APP_VERSION,
        "role": settings.SKYTOWERS_ROLE,
        "device": runtime.device_name,
        "hotel": str(runtime.hotel_id or "")[:8],
        "home": str(home),
        "frozen": bool(getattr(sys, "frozen", False)),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "database_bytes": db.stat().st_size if db.exists() else None,
        "disk_free_bytes": free,
        "migrations": sorted(f"{a}.{n}" for a, n in MigrationRecorder(connection).applied_migrations()),
        "written_at": timezone.now().isoformat(),
    }


def _runs() -> dict:
    from apps.backup.models import BackupRun, ImportRun

    backups = BackupRun.objects.order_by("-created_at").values(
        "created_at", "kind", "status", "seq", "size", "message", "second_error"
    )[:30]
    imports = ImportRun.objects.order_by("-created_at").values(
        "created_at", "status", "file_name", "device", "backup_seq", "checks", "error"
    )[:30]
    return {"backup_runs": list(backups), "import_runs": list(imports)}


def bundle() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("info.json", json.dumps(_info(), ensure_ascii=False, indent=2, default=str))
        zf.writestr("runs.json", json.dumps(_runs(), ensure_ascii=False, indent=2, default=str))
        logs = Path(settings.RUNTIME.home) / "logs"
        for log in sorted(logs.glob("*.log*")) if logs.is_dir() else []:
            data = log.read_bytes()[-MAX_LOG_BYTES:]
            zf.writestr(f"logs/{log.name}", data)
    return buf.getvalue()


def write_to(drive: str, drives: list[dict] | None = None) -> Path:
    """``<drive>\\SkyTowers\\support-<device>-<time>.zip``, through a ``.part`` file."""
    from apps.backup import usb

    known = {d["drive"] for d in (usb.removable_drives() if drives is None else drives)}
    if drive not in known:
        raise ApiError("validation_error", 400, detail="الفلاشة غير موجودة — أدخلها ثم حدّث القائمة.")
    folder = Path(drive) / usb.FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    name = f"support-{settings.RUNTIME.device_name}-{timezone.localtime():%Y%m%d-%H%M}.zip"
    target = folder / name
    part = target.with_name(name + ".part")
    part.write_bytes(bundle())
    part.replace(target)
    return target
