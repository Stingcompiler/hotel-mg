"""«حفظ على فلاشة» (review 2026-09-29, E-16): the backups folder is for Administrators only, so copying a backup to a
USB stick by hand was hard. The service (SYSTEM) sees the removable drives and copies the files itself."""

import ctypes
import shutil
import string
import sys
from pathlib import Path

from apps.core.errors import ApiError

from .models import BackupRun

FOLDER = "SkyTowers"
DRIVE_REMOVABLE = 2


def removable_drives() -> list[dict]:  # pragma: no cover - needs real drives; tests pass ``drives``
    """USB sticks and memory cards with a medium: [{drive: "E:\\", label, free}]. Empty outside Windows."""
    if sys.platform != "win32":
        return []
    kernel32 = ctypes.windll.kernel32
    mask = kernel32.GetLogicalDrives()
    out = []
    for i, letter in enumerate(string.ascii_uppercase):
        root = f"{letter}:\\"
        if not (mask >> i) & 1 or kernel32.GetDriveTypeW(root) != DRIVE_REMOVABLE:
            continue
        try:
            free = shutil.disk_usage(root).free
        except OSError:  # a card reader without a card
            continue
        label = ctypes.create_unicode_buffer(261)
        kernel32.GetVolumeInformationW(root, label, 261, None, None, None, None, 0)
        out.append({"drive": root, "label": label.value, "free": free})
    return out


def _latest() -> BackupRun | None:
    return BackupRun.objects.filter(status=BackupRun.Status.OK).exclude(path="").order_by("-created_at").first()


def copy_latest(drive: str, drives: list[dict] | None = None) -> list[Path]:
    """Copy the newest backup to ``<drive>\\SkyTowers``: every backup holds the whole database and every attachment.
    It is written as ``.part`` first, so a stick pulled out early leaves no half file."""
    known = {d["drive"]: d for d in (removable_drives() if drives is None else drives)}
    if drive not in known:
        raise ApiError("validation_error", 400, detail="الفلاشة غير موجودة — أدخلها ثم حدّث القائمة.")
    latest = _latest()
    if latest is None:
        raise ApiError("validation_error", 400, detail="لا توجد نسخة احتياطية بعد — اضغط «نسخة احتياطية الآن» أولًا.")
    sources = [Path(latest.path)]
    missing = [p.name for p in sources if not p.exists()]
    if missing:
        raise ApiError("validation_error", 400, detail=f"ملف النسخة غير موجود: {missing[0]}")
    if sum(p.stat().st_size for p in sources) > known[drive]["free"]:
        raise ApiError("validation_error", 400, detail="لا توجد مساحة كافية على الفلاشة.")
    target = Path(drive) / FOLDER
    target.mkdir(parents=True, exist_ok=True)
    copied = []
    for source in sources:
        dest = target / source.name
        part = dest.with_name(dest.name + ".part")
        shutil.copyfile(source, part)
        if part.stat().st_size != source.stat().st_size:
            part.unlink(missing_ok=True)
            raise ApiError("validation_error", 400, detail="لم تكتمل الكتابة على الفلاشة — أعد المحاولة.")
        part.replace(dest)
        copied.append(dest)
    return copied
