from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.backup import merge


class Command(BaseCommand):
    help = "Owner PC: import an encrypted backup file (first import, or USB without the app window)."

    def add_arguments(self, parser):
        parser.add_argument("file")
        parser.add_argument("--allow-older", action="store_true")

    def handle(self, *args, file, allow_older=False, **options):
        path = Path(file)
        result = merge.import_backup(
            None, path.read_bytes(), source="file", file_name=path.name, allow_older=allow_older
        )
        for check in result.run.checks:
            self.stdout.write(f"{check['status']:>4}  {check['label']}: {check['detail']}")
        if result.run.status != "ok":
            raise CommandError(result.run.error)
        for table, c in result.run.counts.items():
            self.stdout.write(f"{table}: +{c['inserted']} ~{c['updated']} ={c['ignored']}")
