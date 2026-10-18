"""Open a hotel's backup on a new PC (1.1) — only when the owner chooses to, never as a setup step.

On a reception PC with no hotel records yet (``is_fresh``), «استيراد نسخة» asks one question: view only (the
owner's PC, read-only) or work on this PC (it replaces a reception PC). The file opens with this PC's key or with
the owner's or a manager's own login (key slots); it is checked like any import, the data waits in
``pending-import/`` and the service restarts to take it (service/pending_import.py, then ``finish_pending``).
"""

import json
import logging
import os
import shutil
import threading

from django.conf import settings

from apps.core.errors import ApiError
from service import pending_import

from . import keys, merge, rules
from .models import ImportRun

MODES = ("view", "work")
RESTART_EXIT_CODE = 3  # the service's recovery actions start it again within seconds
log = logging.getLogger(__name__)


def is_fresh() -> bool:
    """A reception PC that holds no hotel records yet: no guest, booking, stay, payment, shift or expense.

    Accounts, a changed password, room types, rooms and settings do not count (owner report 2026-10-18,
    decision 230): changing the default password — which the app asks for first — used to close this door on a
    PC with nothing on it. Opening a backup moves everything here to ``backups/pre-import-<stamp>/`` first.
    """
    from apps.billing.models import Payment
    from apps.cash.models import Expense, Shift
    from apps.guests.models import Guest
    from apps.stays.models import Reservation, Stay

    if settings.SKYTOWERS_ROLE != "reception":
        return False
    return not any(model.objects.exists() for model in (Guest, Reservation, Stay, Payment, Shift, Expense))


def _rejected(exc: merge.ImportRejected) -> ApiError:
    failed = next((c["key"] for c in exc.checks if c.get("status") == "fail"), "")
    code = failed if failed in ("credentials_required", "credentials_wrong") else "backup_rejected"
    return ApiError(code, 400, detail=str(exc))


def prepare(raw: bytes, file_name: str, credentials: tuple[str, str] | None, mode: str, replace: bool = False) -> dict:
    """``replace``: a reception PC that already holds data is restored from the backup (work mode only, owner request
    2026-10-18, decision 231). Its current database and attachments go to ``backups/pre-import-<stamp>/`` as for a
    new PC; nothing is merged or deleted."""
    if mode not in MODES:
        raise ApiError("validation_error", 400)
    if settings.SKYTOWERS_ROLE != "reception":
        raise ApiError("adopt_not_fresh", 409)
    if not is_fresh() and not (replace and mode == "work"):
        raise ApiError("adopt_not_fresh", 409)
    try:
        manifest, files, adopted = merge.open_backup(raw, keys.local_identities(), credentials)
    except merge.ImportRejected as exc:
        raise _rejected(exc) from None
    except Exception:  # noqa: BLE001 - a crafted or damaged file (zip, JSON, header): refused, never a 500
        log.exception("backup could not be opened for adoption")
        detail = "تعذّر فتح النسخة: الملف تالف أو ليس نسخة من هذا البرنامج."
        raise ApiError("backup_rejected", 400, detail=detail) from None
    if rules.mismatched_files(manifest, files):
        raise ApiError("backup_rejected", 400, detail="فشل فحص التوقيع — الملف مُعدَّل أو غير مكتمل.")
    incoming = {tuple(m.split(".", 1)) for m in manifest.get("migrations", [])}
    if rules.unknown_migrations(incoming, merge._known_migrations()):
        raise ApiError("backup_rejected", 400, detail="النسخة من إصدار أحدث من هذا البرنامج — حدّث البرنامج أولًا.")

    pending = pending_import.pending_dir(settings.RUNTIME.home)
    if pending.exists():
        shutil.rmtree(pending)
    pending.mkdir(parents=True)
    db = pending / rules.DB_FILE
    db.write_bytes(files[rules.DB_FILE])
    if merge._integrity(db) != "ok":
        shutil.rmtree(pending)
        raise ApiError("backup_rejected", 400, detail="قاعدة البيانات في النسخة تالفة.")
    if mode == "work":
        for name, data in files.items():
            relative = rules.attachment_path(name)
            if relative is not None:  # a name that would leave the folder is skipped
                dest = pending.joinpath("attachments", *relative)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
    else:
        db.unlink()  # the owner PC merges the file itself after the restart
        (pending / "backup.age").write_bytes(raw)
    if adopted:
        keys.save_hotel_identity(adopted)
    plan = {"mode": mode, "file_name": file_name[:200], "hotel_id": manifest["hotel_id"], "seq": manifest["seq"]}
    (pending / pending_import.PLAN).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    schedule_restart()
    return {"mode": mode, "restarting": True}


def schedule_restart(delay: float = 1.5) -> None:
    """End the process once the answer is sent; Windows' recovery actions start the service again (hooks.nsh)."""
    timer = threading.Timer(delay, os._exit, args=(RESTART_EXIT_CODE,))
    timer.daemon = True
    timer.start()


def finish_pending() -> None:
    """After the migrations: an owner PC merges the adopted backup as its first import, then the folder goes."""
    home = settings.RUNTIME.home
    plan = pending_import.read_plan(home)
    if plan is None or not plan.get("applied"):
        return
    pending = pending_import.pending_dir(home)
    if plan["mode"] == "view":
        raw = (pending / "backup.age").read_bytes()
        result = merge.import_backup(None, raw, source=ImportRun.Source.FILE, file_name=plan["file_name"])
        if result.run.status != ImportRun.Status.OK:
            log.error("adopted backup could not be merged: %s", result.run.error)
            return  # keep the folder for support
    shutil.rmtree(pending, ignore_errors=True)
    log.info("adopted hotel %s (%s); the empty install is kept in %s", plan["hotel_id"], plan["mode"], plan.get("kept"))
