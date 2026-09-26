from datetime import date

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.cash.models import PaymentMethod
from apps.core.fields import MoneyMinorField
from apps.guests.models import Guest
from apps.rooms.models import Room, RoomStatus, RoomType

from . import rules
from .models import DurationKind, Reservation, Stay, StaySegment

BOOKING_KINDS = [(k, v) for k, v in DurationKind.choices if k != DurationKind.MIXED]


class QuoteRequestSerializer(serializers.Serializer):
    room_type = serializers.PrimaryKeyRelatedField(queryset=RoomType.objects.all())
    check_in_date = serializers.DateField()
    duration_kind = serializers.ChoiceField(choices=BOOKING_KINDS)
    count = serializers.IntegerField(min_value=1, max_value=366)


class QuoteOptionSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField(help_text="e.g. «أسبوع + 3 ليالٍ»")
    formula = serializers.CharField(help_text="e.g. «77,000 + 3 × 12,000» (major units)")
    units = serializers.DictField(child=serializers.IntegerField())
    duration_kind = serializers.ChoiceField(choices=DurationKind.choices)
    total = MoneyMinorField()


class QuoteSerializer(serializers.Serializer):
    check_in_date = serializers.DateField()
    check_out_date = serializers.DateField(help_text="Exclusive.")
    last_night = serializers.DateField(help_text="The stay ends at the end of this day.")
    nights = serializers.IntegerField()
    options = QuoteOptionSerializer(many=True, help_text="Cheapest first; the staff choose one when several.")


class AvailableRoomSerializer(serializers.ModelSerializer):
    room_type_name = serializers.CharField(source="room_type.name")

    class Meta:
        model = Room
        fields = ["id", "number", "floor", "room_type", "room_type_name", "status"]


class ReservationSerializer(serializers.ModelSerializer):
    guest_name = serializers.CharField(source="guest.full_name", read_only=True)
    room_number = serializers.CharField(source="room.number", default=None, read_only=True)
    room_type_name = serializers.CharField(source="room_type.name", read_only=True)
    total = MoneyMinorField(read_only=True)
    nights = serializers.IntegerField(read_only=True)
    folio = serializers.UUIDField(source="folio.pk", read_only=True, default=None)
    invoice = serializers.CharField(source="folio.invoice_label", read_only=True, default=None)
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = [
            "id",
            "guest",
            "guest_name",
            "room_type",
            "room_type_name",
            "room",
            "room_number",
            "check_in_date",
            "check_out_date",
            "nights",
            "duration_kind",
            "duration_count",
            "status",
            "total",
            "rate_snapshot",
            "notes",
            "status_reason",
            "folio",
            "invoice",
            "balance",
            "version",
            "created_at",
        ]
        read_only_fields = fields

    def get_balance(self, reservation) -> int | None:
        """Folio balance in minor units (> 0 owed by the guest)."""
        balances = self.context.get("balances")
        if balances is not None:
            return balances.get(reservation.pk)
        from apps.billing.services import FolioTotals

        folio = getattr(reservation, "folio", None)
        return FolioTotals.of(folio).balance if folio else None


class ReservationCreateSerializer(serializers.Serializer):
    guest = serializers.PrimaryKeyRelatedField(queryset=Guest.objects.all())
    room_type = serializers.PrimaryKeyRelatedField(queryset=RoomType.objects.all())
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all(), required=False, allow_null=True)
    check_in_date = serializers.DateField()
    duration_kind = serializers.ChoiceField(choices=BOOKING_KINDS)
    count = serializers.IntegerField(min_value=1, max_value=366)
    option_key = serializers.CharField(required=False, allow_null=True, help_text="From the quote; needed if several.")
    final_total = MoneyMinorField(required=False, allow_null=True, min_value=0, help_text="Price override.")
    override_reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    check_in_now = serializers.BooleanField(default=False, help_text="Walk-in «تسكين الآن»: book and check in at once.")
    discount = MoneyMinorField(required=False, min_value=0, default=0)
    discount_reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    deposit = MoneyMinorField(required=False, min_value=0, default=0, help_text="Taken in the open shift.")
    deposit_method = serializers.ChoiceField(choices=PaymentMethod.choices, default="cash")
    deposit_reference = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    manager_password = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=True,
        default="",
        style={"input_type": "password"},
        help_text="Only for a discount above the hotel's limit.",
    )
    manager_reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class CancelReservationSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300)
    version = serializers.IntegerField(min_value=1, required=False)


class VersionSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1, required=False)


class AssignRoomSerializer(VersionSerializer):
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all())


# --- Stays -------------------------------------------------------------------------------

AFTER_ROOM_STATUS = [("cleaning", "تحتاج تنظيف"), ("maintenance", "صيانة")]


class StaySegmentSerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source="room.number", read_only=True)

    class Meta:
        model = StaySegment
        fields = ["id", "room", "room_number", "from_date", "to_date", "reason"]


class StaySerializer(serializers.ModelSerializer):
    reservation = ReservationSerializer(read_only=True)
    segments = StaySegmentSerializer(many=True, read_only=True)
    override_by_name = serializers.CharField(source="override_by.full_name", default=None, read_only=True)
    last_night = serializers.SerializerMethodField()

    class Meta:
        model = Stay
        fields = [
            "id",
            "reservation",
            "checked_in_at",
            "checked_out_at",
            "last_night",
            "segments",
            "override_by_name",
            "override_reason",
            "version",
        ]

    def get_last_night(self, stay) -> date:
        return rules.last_night(stay.reservation.check_out_date)


class CheckInSerializer(serializers.Serializer):
    reservation = serializers.PrimaryKeyRelatedField(queryset=Reservation.objects.all())
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all(), required=False, allow_null=True)
    version = serializers.IntegerField(min_value=1, required=False)


class ExtendQuoteRequestSerializer(serializers.Serializer):
    duration_kind = serializers.ChoiceField(choices=BOOKING_KINDS)
    count = serializers.IntegerField(min_value=1, max_value=366)


class ExtendQuoteSerializer(serializers.Serializer):
    current_check_out = serializers.DateField()
    quote = QuoteSerializer()
    total_nights = serializers.IntegerField()
    room_available = serializers.BooleanField()


class ExtendSerializer(ExtendQuoteRequestSerializer):
    option_key = serializers.CharField(required=False, allow_null=True)
    final_total = MoneyMinorField(required=False, allow_null=True, min_value=0)
    override_reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    version = serializers.IntegerField(min_value=1, required=False)


class ManagerOverrideMixin(serializers.Serializer):
    override_password = serializers.CharField(
        max_length=128, required=False, allow_blank=True, default="", style={"input_type": "password"}
    )
    override_reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class ChangeRoomOptionSerializer(serializers.Serializer):
    room = AvailableRoomSerializer()
    difference = MoneyMinorField(help_text="Price difference for the remaining nights; 0 for the same type.")


class ChangeRoomSerializer(ManagerOverrideMixin):
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all())
    reason = serializers.CharField(max_length=300)
    old_room_status = serializers.ChoiceField(choices=AFTER_ROOM_STATUS, default="cleaning")
    maintenance_reason = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    version = serializers.IntegerField(min_value=1, required=False)


class CheckoutSerializer(ManagerOverrideMixin):
    room_status = serializers.ChoiceField(choices=AFTER_ROOM_STATUS, default="cleaning")
    maintenance_reason = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    version = serializers.IntegerField(min_value=1, required=False)


class CancelOptionSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    total = MoneyMinorField()


class CancelOptionsSerializer(serializers.Serializer):
    nights_used = serializers.IntegerField()
    current_total = MoneyMinorField()
    options = CancelOptionSerializer(many=True)


class CancelStaySerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300)
    option_key = serializers.CharField(required=False, allow_null=True)
    manual_total = MoneyMinorField(required=False, allow_null=True, min_value=0)
    override_password = serializers.CharField(max_length=128, style={"input_type": "password"})
    override_reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    version = serializers.IntegerField(min_value=1, required=False)


DISPLAY_STATUS = ["ready", "occupied", "cleaning", "maintenance", "overdue"]


class RoomBoardStaySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    reservation = serializers.UUIDField()
    guest_name = serializers.CharField()
    guest_phone = serializers.CharField()
    check_in_date = serializers.DateField()
    check_out_date = serializers.DateField()
    last_night = serializers.DateField()
    days_left = serializers.IntegerField(help_text="0 = ends today; negative = overdue by that many days")
    duration_kind = serializers.ChoiceField(choices=DurationKind.choices)
    duration_label = serializers.CharField()
    balance = MoneyMinorField(allow_null=True)
    invoice = serializers.CharField(allow_null=True)


class RoomBoardNextSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    guest_name = serializers.CharField()
    check_in_date = serializers.DateField()
    duration_kind = serializers.ChoiceField(choices=DurationKind.choices)
    duration_label = serializers.CharField()


class RoomBoardRoomSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    number = serializers.CharField()
    floor = serializers.IntegerField()
    room_type = serializers.UUIDField()
    room_type_name = serializers.CharField()
    status = serializers.ChoiceField(choices=RoomStatus.choices)
    display_status = serializers.ChoiceField(
        choices=DISPLAY_STATUS, help_text="status, or «overdue» when occupied past the end date"
    )
    status_changed_at = serializers.DateTimeField(allow_null=True)
    maintenance_reason = serializers.CharField()
    in_service = serializers.BooleanField()
    manual_targets = serializers.ListField(
        child=serializers.ChoiceField(choices=RoomStatus.choices),
        help_text="Statuses staff may set from the board (rooms/{id}/set-status); maintenance needs a reason.",
    )
    version = serializers.IntegerField()
    stay = RoomBoardStaySerializer(allow_null=True)
    next_reservation = RoomBoardNextSerializer(allow_null=True)


class RoomBoardSummarySerializer(serializers.Serializer):
    rooms = serializers.IntegerField()
    occupied = serializers.IntegerField()
    occupancy_percent = serializers.IntegerField()
    arrivals_today = serializers.IntegerField()
    departures_today = serializers.IntegerField()
    overdue = serializers.IntegerField()
    by_status = serializers.DictField(child=serializers.IntegerField())


class RoomBoardSerializer(serializers.Serializer):
    date = serializers.DateField()
    summary = RoomBoardSummarySerializer()
    rooms = RoomBoardRoomSerializer(many=True)


class StayGuestSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    phone = serializers.CharField()
    nationality = serializers.CharField()
    id_type_label = serializers.CharField()
    id_number = serializers.CharField(help_text="Full for manager/owner; last 4 characters otherwise.")
    warning_note = serializers.CharField()
    companions = serializers.ListField(child=serializers.DictField(child=serializers.CharField()))


class StayRoomSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    number = serializers.CharField()
    floor = serializers.IntegerField()
    room_type_name = serializers.CharField()
    status = serializers.ChoiceField(choices=RoomStatus.choices)
    display_status = serializers.ChoiceField(choices=DISPLAY_STATUS)


class StayLogEntrySerializer(serializers.Serializer):
    at = serializers.DateTimeField()
    action = serializers.CharField()
    label = serializers.CharField()
    by = serializers.CharField(allow_null=True)


class StayDetailSerializer(StaySerializer):
    """Stay detail 6.5: the stay plus the guest card, the room line, days left and the activity log."""

    guest = serializers.SerializerMethodField()
    room = serializers.SerializerMethodField()
    days_left = serializers.SerializerMethodField(help_text="0 = ends today; negative = overdue; null once closed")
    log = serializers.SerializerMethodField(
        help_text="Audit rows of this stay, its reservation and folio; newest first"
    )

    class Meta(StaySerializer.Meta):
        fields = [*StaySerializer.Meta.fields, "guest", "room", "days_left", "log"]

    @extend_schema_field(StayGuestSerializer)
    def get_guest(self, stay):
        from apps.accounts import rules as account_rules
        from apps.guests import rules as guest_rules

        g = stay.reservation.guest
        user = self.context["request"].user
        return {
            "id": g.pk,
            "full_name": g.full_name,
            "phone": g.phone,
            "nationality": g.nationality,
            "id_type_label": g.get_id_type_display() if g.id_type else "",
            "id_number": g.id_number
            if account_rules.is_manager(user.role)
            else guest_rules.mask_id_number(g.id_number),
            "warning_note": g.warning_note,
            "companions": [{"name": c.name, "relation": c.relation} for c in g.companions.filter(removed=False)],
        }

    @extend_schema_field(StayRoomSerializer(allow_null=True))
    def get_room(self, stay):
        from apps.rooms import rules as room_rules

        room = stay.reservation.room
        if room is None:
            return None
        overdue = stay.checked_out_at is None and room_rules.is_overdue(
            room.status, services_today(), stay.reservation.check_out_date
        )
        return {
            "id": room.pk,
            "number": room.number,
            "floor": room.floor,
            "room_type_name": stay.reservation.room_type.name,
            "status": room.status,
            "display_status": "overdue" if overdue else room.status,
        }

    def get_days_left(self, stay) -> int | None:
        if stay.checked_out_at is not None:
            return None
        return (rules.last_night(stay.reservation.check_out_date) - services_today()).days

    @extend_schema_field(StayLogEntrySerializer(many=True))
    def get_log(self, stay):
        from apps.audit import rules as audit_rules
        from apps.audit.models import AuditLog

        ids = [str(stay.pk), str(stay.reservation_id)]
        folio = getattr(stay.reservation, "folio", None)
        if folio is not None:
            ids.append(str(folio.pk))
        rows = AuditLog.objects.filter(entity_id__in=ids).select_related("actor").order_by("-seq")
        return [
            {
                "at": r.at,
                "action": r.action,
                "label": audit_rules.action_label(r.action),
                "by": r.actor.full_name if r.actor_id else None,
            }
            for r in rows
        ]


def services_today():
    from .services import today

    return today()
