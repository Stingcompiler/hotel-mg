from rest_framework import serializers

from apps.core.fields import MoneyMinorField
from apps.guests.models import Guest
from apps.rooms.models import Room, RoomType

from .models import DurationKind, Reservation

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

    class Meta:
        model = Reservation
        fields = [
            "id", "guest", "guest_name", "room_type", "room_type_name", "room", "room_number",
            "check_in_date", "check_out_date", "nights", "duration_kind", "duration_count", "status",
            "total", "rate_snapshot", "notes", "status_reason", "version", "created_at",
        ]  # fmt: skip
        read_only_fields = fields


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


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300)
    version = serializers.IntegerField(min_value=1, required=False)


class VersionSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1, required=False)


class AssignRoomSerializer(VersionSerializer):
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all())
