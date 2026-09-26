from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core.seed import demo_data
from apps.rooms.models import Room, RoomStatusHistory, RoomType


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
            users = self._load_users()
            types, rooms = self._load_rooms()

        self.stdout.write(self.style.SUCCESS(f"Created: {users} users, {types} room types, {rooms} rooms."))

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

    def _load_rooms(self) -> tuple[int, int]:
        """Room types, 30 rooms and their non-occupied states. Idempotent by name/number."""
        manager = User.objects.filter(role="manager").first()
        types = {}
        created_types = 0
        for row in demo_data.ROOM_TYPES:
            room_type, created = RoomType.objects.get_or_create(
                name=row["name"],
                defaults={
                    "capacity": row["capacity"],
                    "nightly_price": row["nightly"],
                    "weekly_price": row["weekly"],
                    "monthly_price": row["monthly"],
                    "created_by": manager,
                },
            )
            types[row["name"]] = room_type
            created_types += created

        created_rooms = 0
        now = timezone.now()
        for row in demo_data.ROOMS:
            if Room.objects.filter(number=row["number"]).exists():
                continue
            state = demo_data.ROOM_STATES.get(row["number"], {})
            room = Room.objects.create(
                number=row["number"],
                floor=row["floor"],
                room_type=types[row["type"]],
                status=state.get("status", "ready"),
                maintenance_reason=state.get("maintenance_reason", ""),
                status_changed_at=now,
                created_by=manager,
            )
            if room.status != "ready":
                RoomStatusHistory.objects.create(
                    room=room, from_status="ready", to_status=room.status, at=now,
                    reason=room.maintenance_reason, created_by=manager,
                )  # fmt: skip
            created_rooms += 1
        return created_types, created_rooms
