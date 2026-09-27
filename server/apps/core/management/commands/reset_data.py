"""Start this PC over with an empty database (the first-run setup page), e.g. after a trial with the demo hotel.

Nothing is deleted: the database, attachments and backup files move to ``backups/pre-reset-<stamp>/``.
``config.json``, the secret and the owner's key stay, so the reception↔owner pairing keeps working; an owner
PC forgets the hotel id so its next first import adopts the hotel again. The service must be stopped first.

    skytowers-server.exe manage reset_data --yes
"""

import json
import shutil
from datetime import datetime

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from apps.backup.management.commands.restore_full import Command as RestoreFull


class Command(BaseCommand):
    # An owner PC may have no hotel id yet; the model checks would need one.
    requires_system_checks = []
    help = "Empty this PC's data (moved to backups/pre-reset-<stamp>/); the app opens on the first-run setup."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")

    def handle(self, *args, yes=False, **options):
        runtime = settings.RUNTIME
        keep = runtime.backups_dir / f"pre-reset-{datetime.now():%Y%m%d-%H%M%S}"
        if not yes:
            answer = input(f"ستُنقل بيانات هذا الجهاز إلى {keep} ويبدأ البرنامج فارغًا. متابعة؟ [y/N] ")
            if answer.strip().lower() not in ("y", "yes"):
                raise CommandError("أُلغي.")

        connections.close_all()
        RestoreFull._refuse_if_in_use(runtime.db_path)
        keep.mkdir(parents=True, exist_ok=True)
        moved = 0
        for name in ("hotel.db", "hotel.db-wal", "hotel.db-shm"):
            current = runtime.data_dir / name
            if current.exists():
                shutil.move(str(current), str(keep / name))
                moved += 1
        if runtime.attachments_dir.exists():
            shutil.move(str(runtime.attachments_dir), str(keep / "attachments"))
        # Backup files of the old data would otherwise sit in the new hotel's backup list.
        for backup in runtime.backups_dir.glob("*.age"):
            shutil.move(str(backup), str(keep / backup.name))
            moved += 1

        if runtime.role == "owner":
            config_file = runtime.home / "config.json"
            if config_file.exists():
                raw = json.loads(config_file.read_text(encoding="utf-8"))
                raw["hotel_id"] = ""
                config_file.write_text(json.dumps(raw, indent=2), encoding="utf-8")

        runtime.data_dir.mkdir(parents=True, exist_ok=True)
        call_command("migrate", "-v0")
        self.stdout.write(f"تم: البرنامج فارغ الآن. البيانات السابقة ({moved} ملفًا) في {keep}")
