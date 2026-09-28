from rest_framework import serializers

from apps.core.fields import MoneyMinorField
from apps.core.serializers import VersionRequiredMixin

from .models import Room, RoomStatus, RoomStatusHistory, RoomType


class RoomTypeSerializer(serializers.ModelSerializer):
    nightly_price = MoneyMinorField(min_value=0)
    weekly_price = MoneyMinorField(min_value=0)
    monthly_price = MoneyMinorField(min_value=0)
    room_count = serializers.IntegerField(read_only=True, default=None)

    class Meta:
        model = RoomType
        fields = [
            "id",
            "name",
            "capacity",
            "nightly_price",
            "weekly_price",
            "monthly_price",
            "is_active",
            "room_count",
            "version",
        ]
        read_only_fields = ["id", "version"]

    def validate_name(self, value):
        qs = RoomType.objects.filter(name=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("يوجد نوع غرفة بهذا الاسم.")
        return value


class RoomTypeUpdateSerializer(VersionRequiredMixin, RoomTypeSerializer):
    version = serializers.IntegerField(min_value=1)

    class Meta(RoomTypeSerializer.Meta):
        read_only_fields = ["id"]
        extra_kwargs = {f: {"required": False} for f in ["name", "capacity", "is_active"]}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("nightly_price", "weekly_price", "monthly_price"):
            self.fields[name].required = False


class RoomSerializer(serializers.ModelSerializer):
    room_type_name = serializers.CharField(source="room_type.name", read_only=True)

    class Meta:
        model = Room
        fields = [
            "id",
            "number",
            "name",
            "floor",
            "room_type",
            "room_type_name",
            "status",
            "status_changed_at",
            "maintenance_reason",
            "in_service",
            "note",
            "version",
        ]
        read_only_fields = ["id", "status", "status_changed_at", "maintenance_reason", "version"]

    def validate_number(self, value):
        qs = Room.objects.filter(number=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("يوجد غرفة بهذا الرقم.")
        return value


class RoomCreateSerializer(RoomSerializer):
    class Meta(RoomSerializer.Meta):
        fields = ["number", "name", "floor", "room_type", "note"]
        read_only_fields = []


class RoomUpdateSerializer(VersionRequiredMixin, RoomSerializer):
    version = serializers.IntegerField(min_value=1)

    class Meta(RoomSerializer.Meta):
        fields = ["number", "name", "floor", "room_type", "note", "in_service", "version"]
        read_only_fields = []
        extra_kwargs = {f: {"required": False} for f in ["number", "name", "floor", "room_type", "note", "in_service"]}


class SetStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=RoomStatus.choices)
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    version = serializers.IntegerField(min_value=1, required=False)


class RoomStatusHistorySerializer(serializers.ModelSerializer):
    by_name = serializers.CharField(source="created_by.full_name", default=None, read_only=True)

    class Meta:
        model = RoomStatusHistory
        fields = ["id", "from_status", "to_status", "at", "reason", "by_name"]
