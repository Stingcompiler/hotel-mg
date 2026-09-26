import time

from django.core.management.base import BaseCommand

from apps.followups import engine


class Command(BaseCommand):
    help = "Run the alert engine: once, or every 60 s (the Windows service runs it in a thread)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=int, default=60)

    def handle(self, *args, once=False, interval=60, **options):
        while True:
            self.stdout.write(str(engine.tick()))
            if once:
                return
            time.sleep(interval)
