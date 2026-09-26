"""Additive merge import on the owner PC (spec §9.3). Nothing is ever deleted.

decrypt → verify SHA-256 of every file → integrity_check → hotel_id → version (unknown migrations) →
attach as the ``incoming`` database and migrate it → verify its audit chain → one transaction on the
target: insert absent rows; update mutable rows only where incoming.updated_at is newer → copy absent
attachments → record counts. Any failure: rollback, ``ImportRun`` failed, local data untouched.
"""

import copy
import dataclasses
import io
import json
import sqlite3
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pyrage
from django.apps import apps as django_apps
from django.conf import settings
from django.core.management import call_command
from django.db import connections, transaction
from django.db.migrations.loader import MigrationLoader

from apps.audit import services as audit_services
from apps.core.models import AppendOnlyModel

from . import keys, rules
from .models import ImportRun

INCOMING = "incoming"

# Hotel data merged in dependency order, with the table label of the result screen (artboard 6.13 C).
# Device state is not merged: clock, sequences, sessions/tokens, backup runs and settings, toasts.
MERGE_ORDER = [
    ("accounts.User", "المستخدمون"),
    ("accounts.LoginEvent", "المستخدمون"),
    ("core.HotelSettings", "الإعدادات"),
    ("rooms.RoomType", "الغرف"),
    ("rooms.Room", "الغرف"),
    ("rooms.RoomStatusHistory", "الغرف"),
    ("guests.Guest", "النزلاء"),
    ("guests.Companion", "النزلاء"),
    ("guests.GuestDocument", "النزلاء"),
    ("stays.Reservation", "الإقامات"),
    ("stays.Stay", "الإقامات"),
    ("stays.StaySegment", "الإقامات"),
    ("billing.Folio", "الإقامات"),
    ("billing.FolioLine", "الإقامات"),
    ("cash.Shift", "الورديات"),
    ("cash.Expense", "المصروفات"),
    ("cash.ExpenseAttachment", "المصروفات"),
    ("billing.Payment", "الدفعات"),
    ("followups.AlertRule", "التنبيهات والاستجابة"),
    ("followups.FollowupTask", "التنبيهات والاستجابة"),
    ("followups.TaskAction", "التنبيهات والاستجابة"),
    ("audit.AuditLog", "سجل التدقيق"),
]


class ImportRejected(Exception):
    def __init__(self, message: str, checks: list[dict]):
        super().__init__(message)
        self.checks = checks


@dataclass
class ImportResult:
    run: ImportRun
    counts: dict = field(default_factory=dict)


# --- Reading the file -------------------------------------------------------------------------


def _open(raw: bytes, identity) -> tuple[dict, dict[str, bytes]]:
    try:
        archive = pyrage.decrypt(raw, [identity])
    except Exception:  # noqa: BLE001 - wrong key, truncated or tampered ciphertext
        raise ImportRejected(
            "فشل فحص التوقيع — الملف مُعدَّل أو غير مكتمل أو ليس لهذا الجهاز.",
            [rules.check("signature", "التوقيع", "تعذّر فك التشفير", "fail")],
        ) from None
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        files = {name: zf.read(name) for name in zf.namelist()}
    manifest = json.loads(files.pop(rules.MANIFEST))
    return manifest, files


def _known_migrations() -> set[tuple[str, str]]:
    return set(MigrationLoader(None, ignore_no_migrations=True).disk_migrations)


def _integrity(db_path: Path) -> str:
    con = sqlite3.connect(db_path)
    try:
        return con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()


def _attach(db_path: Path, target: str) -> None:
    """Point the ``incoming`` alias at the backup copy and migrate it."""
    config = copy.deepcopy(connections[target].settings_dict)
    config["NAME"] = str(db_path)
    config["TEST"] = {"NAME": str(db_path)}
    _drop_alias()
    connections.databases[INCOMING] = config
    call_command("migrate", database=INCOMING, verbosity=0, interactive=False)


def _drop_alias() -> None:
    if INCOMING in connections.databases:
        connections[INCOMING].close()
        del connections[INCOMING]
        del connections.databases[INCOMING]


class _IncomingAlias:
    """Restores whatever ``incoming`` was before the import (tests declare it), even after an error."""

    def __enter__(self):
        self.previous = copy.deepcopy(connections.databases.get(INCOMING))
        return self

    def __exit__(self, *exc):
        _drop_alias()
        if self.previous is not None:
            connections.databases[INCOMING] = self.previous
        return False


# --- Merge --------------------------------------------------------------------------------------


class _KeepTimestamps:
    """Rows must keep the reception's ``updated_at``: bulk_create would stamp them with the import time and
    every later edit on the reception would then look older than the owner's copy (spec §9.3.6)."""

    def __init__(self, models):
        self.fields = [f for m in models for f in m._meta.concrete_fields if getattr(f, "auto_now", False)]

    def __enter__(self):
        for f in self.fields:
            f.auto_now = False

    def __exit__(self, *exc):
        for f in self.fields:
            f.auto_now = True
        return False


def _merge_model(model, hotel_id: str, target: str) -> dict:
    counts = {"inserted": 0, "updated": 0, "ignored": 0}
    append_only = issubclass(model, AppendOnlyModel)
    fields = [f for f in model._meta.concrete_fields if not f.primary_key]
    incoming = model.objects.using(INCOMING).filter(hotel_id=hotel_id).order_by("pk")
    batch = []

    def flush(rows):
        ids = [r.pk for r in rows]
        existing = dict(model.objects.using(target).filter(pk__in=ids).values_list("pk", "updated_at"))
        new = [r for r in rows if r.pk not in existing]
        for r in new:
            r._state.db = target
        model.objects.using(target).bulk_create(new, ignore_conflicts=True)
        counts["inserted"] += len(new)
        for r in rows:
            if r.pk not in existing:
                continue
            if append_only or r.updated_at <= existing[r.pk]:
                counts["ignored"] += 1
                continue
            values = {f.attname: getattr(r, f.attname) for f in fields}
            model._base_manager.using(target).filter(pk=r.pk).update(**values)
            counts["updated"] += 1

    for row in incoming.iterator(chunk_size=500):
        batch.append(row)
        if len(batch) == 500:
            flush(batch)
            batch = []
    if batch:
        flush(batch)
    return counts


def _copy_attachments(files: dict[str, bytes]) -> int:
    copied = 0
    root = settings.RUNTIME.attachments_dir
    for name, data in files.items():
        if not name.startswith("attachments/"):
            continue
        dest = root / name.removeprefix("attachments/")
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            copied += 1
    return copied


def _set_hotel_id(hotel_id: str) -> None:
    """First import on the owner PC: adopt the reception's hotel_id (spec §9.3.3)."""
    config_file = settings.RUNTIME.home / "config.json"
    data = json.loads(config_file.read_text(encoding="utf-8")) if config_file.exists() else {"role": "owner"}
    data["hotel_id"] = hotel_id
    config_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    settings.RUNTIME = dataclasses.replace(settings.RUNTIME, hotel_id=uuid.UUID(hotel_id))


def last_imported(target: str = "default") -> ImportRun | None:
    return ImportRun.objects.using(target).filter(status=ImportRun.Status.OK).order_by("-backup_seq").first()


def import_backup(
    actor, raw: bytes, *, source: str, file_name: str, allow_older: bool = False, target: str = "default", identity=None
) -> ImportResult:
    """Run the five checks, then merge. Returns the ImportRun (ok or failed); never raises for bad files."""
    checks: list[dict] = []
    manifest: dict = {}
    identity = identity or keys.load()
    tmp_root = settings.RUNTIME.home / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        with _IncomingAlias(), tempfile.TemporaryDirectory(dir=tmp_root) as tmp:
            manifest, files = _open(raw, identity)
            bad = rules.mismatched_files(manifest, files)
            checks.append(
                rules.check(
                    "signature",
                    "التوقيع",
                    "SHA-256 · مطابق" if not bad else f"غير مطابق: {', '.join(bad[:3])}",
                    "ok" if not bad else "fail",
                )
            )
            if bad:
                raise ImportRejected("فشل فحص التوقيع — الملف مُعدَّل أو غير مكتمل.", checks)

            db_path = Path(tmp) / rules.DB_FILE
            db_path.write_bytes(files[rules.DB_FILE])
            integrity = _integrity(db_path)
            checks.append(
                rules.check(
                    "integrity",
                    "سلامة القاعدة",
                    f"PRAGMA integrity_check · {integrity}",
                    "ok" if integrity == "ok" else "fail",
                )
            )
            if integrity != "ok":
                raise ImportRejected("قاعدة البيانات في النسخة تالفة.", checks)

            ours = settings.RUNTIME.hotel_id
            theirs = manifest["hotel_id"]
            same_hotel = ours is None or str(ours) == theirs
            checks.append(rules.check("hotel", "معرف الفندق", theirs[:8], "ok" if same_hotel else "fail"))
            if not same_hotel:
                raise ImportRejected("النسخة من فندق آخر.", checks)

            incoming_migrations = {tuple(m.split(".", 1)) for m in manifest.get("migrations", [])}
            newer = rules.unknown_migrations(incoming_migrations, _known_migrations())
            checks.append(
                rules.check(
                    "version",
                    "الإصدار",
                    f"v{manifest.get('app_version')} → v{settings.APP_VERSION}",
                    "fail" if newer else "ok",
                )
            )
            if newer:
                raise ImportRejected("النسخة من إصدار أحدث من هذا البرنامج — حدّث البرنامج أولًا.", checks)

            last = last_imported(target)
            older = bool(last and last.backup_seq and manifest["seq"] < last.backup_seq)
            _attach(db_path, target)
            broken = audit_services.verify_chain(theirs, using=INCOMING)
            if broken is not None:
                checks.append(rules.check("audit", "سلسلة التدقيق", f"انقطاع عند القيد {broken}", "fail"))
                raise ImportRejected("سلسلة التدقيق في النسخة منقطعة.", checks)
            prev = last.backup_seq if last else "—"
            checks.append(
                rules.check(
                    "audit",
                    "سلسلة التدقيق",
                    f"{manifest['seq']} < {prev} · أقدم من البيانات الحالية"
                    if older
                    else f"{prev} → {manifest['seq']} · متصلة",
                    "warn" if older else "ok",
                )
            )
            if older and not allow_older:
                raise ImportRejected("هذا الملف أقدم من البيانات الحالية.", checks)

            counts: dict = {}
            merge_models = [django_apps.get_model(name) for name, _ in MERGE_ORDER]
            with transaction.atomic(using=target), _KeepTimestamps(merge_models):
                for label_model, label in MERGE_ORDER:
                    model = django_apps.get_model(label_model)
                    c = _merge_model(model, theirs, target)
                    total = counts.setdefault(label, {"inserted": 0, "updated": 0, "ignored": 0})
                    for k in total:
                        total[k] += c[k]
                run = ImportRun.objects.using(target).create(
                    hotel_id=theirs,
                    source=source,
                    file_name=file_name[:200],
                    backup_seq=manifest["seq"],
                    data_as_of=datetime.fromisoformat(manifest["created_at"]),
                    status=ImportRun.Status.OK,
                    counts=counts,
                    checks=checks,
                    audit_chain_ok=True,
                    created_by_id=actor.pk if actor else None,
                )
            _copy_attachments(files)
            if settings.RUNTIME.hotel_id is None and target == "default":
                _set_hotel_id(theirs)
            return ImportResult(run, counts)
    except ImportRejected as exc:
        return ImportResult(_failed(target, source, file_name, manifest, exc.checks, str(exc), actor))
    except Exception as exc:  # noqa: BLE001 - corrupt zip, missing files, DB errors: reject, keep data
        return ImportResult(_failed(target, source, file_name, manifest, checks, f"تعذّر الاستيراد: {exc}", actor))


def _failed(target, source, file_name, manifest, checks, message, actor) -> ImportRun:
    hotel_id = manifest.get("hotel_id") or settings.RUNTIME.hotel_id
    with transaction.atomic(using=target):
        return ImportRun.objects.using(target).create(
            hotel_id=hotel_id or "00000000-0000-0000-0000-000000000000",
            source=source,
            file_name=file_name[:200],
            backup_seq=manifest.get("seq"),
            status=ImportRun.Status.FAILED,
            checks=checks,
            audit_chain_ok=None,
            error=message[:300],
            created_by_id=actor.pk if actor else None,
        )


def save_incoming_file(raw: bytes, name: str) -> Path:
    """Keep a copy of imported files under ``incoming/`` (USB or Drive)."""
    folder = settings.RUNTIME.home / "incoming"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / Path(name).name
    path.write_bytes(raw)
    return path
