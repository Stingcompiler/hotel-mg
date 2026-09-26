from django.core.management.base import BaseCommand

from apps.backup import export


class Command(BaseCommand):
    help = "Write an encrypted backup now (tray menu «نسخة احتياطية الآن»)."

    def handle(self, *args, **options):
        run = export.run_backup(kind="manual")
        self.stdout.write(f"{run.status} {run.path or run.message}")
