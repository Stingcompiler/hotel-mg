from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.billing import services as billing
from apps.cash import services as cash
from apps.cash.models import Shift
from apps.core.seed import demo_data
from apps.guests import rules as guest_rules
from apps.guests.models import Guest
from apps.rooms.models import Room, RoomStatusHistory, RoomType
from apps.stays import rules as stay_rules
from apps.stays import services as reservation_services
from apps.stays import stay_services
from apps.stays.models import Reservation


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
            stays, bookings = self._load_stays()
            payments, expenses = self._load_money()

        self.stdout.write(
            self.style.SUCCESS(
                f"Created: {users} users, {types} room types, {rooms} rooms, {stays} stays, {bookings} reservations, "
                f"{payments} payments, {expenses} expenses."
            )
        )

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
                    room=room,
                    from_status="ready",
                    to_status=room.status,
                    at=now,
                    reason=room.maintenance_reason,
                    created_by=manager,
                )
            created_rooms += 1
        return created_types, created_rooms

    def _guest(self, row, actor) -> Guest:
        guest = Guest.objects.filter(full_name=row["guest"]).first()
        if guest:
            return guest
        return Guest.objects.create(
            full_name=row["guest"],
            search_name=guest_rules.normalize_name(row["guest"]),
            phone=guest_rules.normalize_phone(row.get("phone", "")),
            nationality=row.get("nationality", "سوداني"),
            id_type=row.get("id_type", ""),
            id_number=row.get("id_number", ""),
            warning_note=row.get("warning_note", ""),
            created_by=actor,
        )

    def _load_stays(self) -> tuple[int, int]:
        """Checked-in stays and upcoming bookings from the Room Board, dated relative to today."""
        actor = User.objects.get(username="ahmed.ali")
        today = reservation_services.today()
        stays = 0
        for row in demo_data.STAYS:
            room = Room.objects.get(number=row["room"])
            if Reservation.objects.filter(room=room, status="checked_in").exists():
                continue
            nights = stay_rules.nights_for(row["kind"], row["count"])
            check_out = today + timedelta(days=row["ends_in"] + 1)
            reservation = reservation_services.create_reservation(
                actor,
                guest=self._guest(row, actor),
                room_type=room.room_type,
                room=room,
                check_in_date=check_out - timedelta(days=nights),
                duration_kind=row["kind"],
                count=row["count"],
                allow_past=True,
            )
            stay_services.record_check_in(actor, reservation, room)
            stays += 1

        bookings = 0
        for row in demo_data.RESERVATIONS:
            room = Room.objects.get(number=row["room"])
            if Reservation.objects.filter(room=room, status="confirmed").exists():
                continue
            reservation_services.create_reservation(
                actor,
                guest=self._guest(row, actor),
                room_type=room.room_type,
                room=room,
                check_in_date=today + timedelta(days=row["starts_in"]),
                duration_kind=row["kind"],
                count=row["count"],
            )
            bookings += 1
        return stays, bookings

    def _load_money(self) -> tuple[int, int]:
        """Earlier payments leave the brief's balances (203: 15,000, 305: 42,000, others settled); today's
        shift opens with 50,000 and the two expenses of the Expenses artboard."""
        if Shift.objects.exists():
            return 0, 0
        actor = User.objects.get(username="ahmed.ali")
        manager = User.objects.get(username="manager")
        payments = 0
        cash.open_shift(manager, opening=0)  # back-office shift for payments taken before today
        for reservation in Reservation.objects.filter(status="checked_in").select_related("room"):
            folio = billing.folio_of(reservation)
            due = billing.FolioTotals.of(folio).balance - demo_data.BALANCES.get(reservation.room.number, 0)
            if due > 0:
                billing.take_payment(
                    manager, folio, amount=due, method="bankak", reference=f"BOK-{70000 + payments:05d}"
                )
                payments += 1
        cash.close_shift(manager, counted=0)
        cash.open_shift(actor, opening=demo_data.SHIFT["opening"])
        for row in demo_data.EXPENSES:
            cash.create_expense(actor, **row)
        return payments, len(demo_data.EXPENSES)
