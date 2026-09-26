from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.core.seed import demo_data


class Command(BaseCommand):
    help = "Load the design brief's sample data (idempotent). Development and review only."

    def add_arguments(self, parser):
        parser.add_argument(
            "--allow-non-debug",
            action="store_true",
            help="Run even when DEBUG is off (tests, review builds). Never on a hotel PC.",
        )

    def handle(self, *args, allow_non_debug=False, **options):
        if not settings.DEBUG and not allow_non_debug:
            raise CommandError("seed_demo creates users with known PINs; refusing to run with DEBUG off.")
        if settings.SKYTOWERS_ROLE != "reception":
            raise CommandError("seed_demo runs on the reception role only; the owner PC gets data by import.")

        with transaction.atomic():
            created = self._load_users()

        self.stdout.write(self.style.SUCCESS(f"Users: {created} created, {len(demo_data.USERS) - created} existing."))

    def _load_users(self) -> int:
        created = 0
        for row in demo_data.USERS:
            if User.objects.filter(username=row["username"]).exists():
                continue
            User.objects.create_user(
                row["username"],
                row["full_name"],
                role=row["role"],
                password=demo_data.DEMO_PASSWORD,
                pin=demo_data.DEMO_PIN,
                is_active=row["is_active"],
                is_staff=row["role"] == "manager",
            )
            created += 1
        return created
