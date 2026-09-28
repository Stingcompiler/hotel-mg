"""Disaster recovery on a reception PC (spec §9.3): replace the database and attachments with a backup file.

The file is encrypted to the owner's key, so the owner PC's identity file must be copied here for the
duration of the restore. The service must be stopped first; the command refuses to run while the database
is in use, keeps the current files under ``backups/pre-restore-<stamp>/`` and runs the migrations afterwards.
"""

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from apps.backup import keys, merge, rules

IN_USE = "قاعدة البيانات مستعملة الآن — أوقف خدمة Sky Towers Server أولًا وانتظر حتى تتوقف تمامًا."


class Command(BaseCommand):
    requires_system_checks = []
    help = "Reception PC: restore the whole database and attachments from an encrypted backup (service stopped)."

    def add_arguments(self, parser):
        parser.add_argument("file", help="skytowers-<hotel8>-<seq>-<stamp>.age")
        parser.add_argument("--identity", required=True, help="the owner PC's owner.key file (copied for the restore)")
        parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")

    def handle(self, *args, file, identity, yes=False, **options):
        runtime = settings.RUNTIME
        if runtime.role != "reception":
            raise CommandError("restore_full runs on the reception PC only; the owner PC imports instead.")
        path, key_path = Path(file), Path(identity)
        if not path.is_file():
            raise CommandError(f"الملف غير موجود: {path}")
        if not key_path.is_file():
            raise CommandError(f"ملف المفتاح غير موجود: {key_path}")
        try:
            manifest, files = merge._open(path.read_bytes(), keys.load(key_path))
        except merge.ImportRejected as e:
            raise CommandError(str(e)) from None
        if rules.DB_FILE not in files:
            raise CommandError("النسخة لا تحتوي قاعدة البيانات.")
        hotel8 = str(manifest.get("hotel_id", "")).replace("-", "")[:8]
        mine8 = str(runtime.hotel_id or "").replace("-", "")[:8]
        if runtime.hotel_id and hotel8 != mine8:
            raise CommandError(f"النسخة لفندق آخر ({hotel8} ≠ {mine8}).")
        bad = rules.mismatched_files(manifest, files)
        if bad:
            raise CommandError(f"ملفات تالفة في النسخة: {', '.join(bad)}")

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        keep = runtime.backups_dir / f"pre-restore-{stamp}"
        self.stdout.write(f"النسخة رقم {manifest.get('seq')} من {manifest.get('created_at')} · {len(files) - 1} مرفقًا")
        if not yes:
            answer = input(f"سيُستبدل {runtime.db_path} (نسخة الحالي في {keep}). متابعة؟ [y/N] ")
            if answer.strip().lower() not in ("y", "yes"):
                raise CommandError("أُلغي.")

        connections.close_all()
        self._refuse_if_in_use(runtime.db_path)
        keep.mkdir(parents=True, exist_ok=True)
        for name in ("hotel.db", "hotel.db-wal", "hotel.db-shm"):
            current = runtime.data_dir / name
            if current.exists():
                shutil.move(str(current), str(keep / name))
        if runtime.attachments_dir.exists():
            shutil.move(str(runtime.attachments_dir), str(keep / "attachments"))

        runtime.data_dir.mkdir(parents=True, exist_ok=True)
        runtime.db_path.write_bytes(files[rules.DB_FILE])
        if (result := merge._integrity(runtime.db_path)) != "ok":
            raise CommandError(f"قاعدة البيانات في النسخة تالفة: {result}")
        runtime.attachments_dir.mkdir(parents=True, exist_ok=True)
        restored = 0
        for name, data in files.items():
            relative = rules.attachment_path(name)
            if relative is not None:  # a name that would leave the folder is skipped
                dest = runtime.attachments_dir.joinpath(*relative)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                restored += 1
        call_command("migrate", "-v0")
        self.stdout.write(f"تم: قاعدة البيانات و{restored} مرفقًا. الملفات السابقة في {keep}")

    @staticmethod
    def _refuse_if_in_use(db_path: Path) -> None:
        if not db_path.exists():
            return
        try:
            con = sqlite3.connect(db_path, timeout=1)
            try:
                con.execute("BEGIN IMMEDIATE")
                con.rollback()
            finally:
                con.close()
        except sqlite3.OperationalError:
            raise CommandError(IN_USE) from None
        except sqlite3.DatabaseError:
            pass  # a corrupt current file is exactly what a restore replaces
        # On Windows a process that merely has the file open (a service still stopping) blocks moving it even
        # when no write is in progress: find out before anything is moved.
        probe = db_path.with_name(db_path.name + ".move-check")
        try:
            os.replace(db_path, probe)
        except PermissionError:
            raise CommandError(IN_USE) from None
        os.replace(probe, db_path)
