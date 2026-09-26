from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts import rules as account_rules

from . import rules
from .models import Companion, Guest, GuestDocument, IdType


class CompanionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Companion
        fields = ["name", "relation"]


class GuestDocumentSerializer(serializers.ModelSerializer):
    added_by = serializers.CharField(source="created_by.full_name", default=None, read_only=True)

    class Meta:
        model = GuestDocument
        fields = ["id", "size", "created_at", "added_by"]


class GuestSerializer(serializers.ModelSerializer):
    companions = serializers.SerializerMethodField()
    documents = GuestDocumentSerializer(many=True, read_only=True)
    id_number = serializers.SerializerMethodField(help_text="Full for manager/owner; last 4 characters otherwise.")

    class Meta:
        model = Guest
        fields = [
            "id",
            "full_name",
            "phone",
            "nationality",
            "id_type",
            "id_number",
            "warning_note",
            "companions",
            "documents",
            "version",
            "created_at",
        ]

    def get_companions(self, guest) -> list[dict]:
        return CompanionSerializer(guest.companions.filter(removed=False), many=True).data

    def get_id_number(self, guest) -> str:
        user = self.context["request"].user
        return guest.id_number if account_rules.is_manager(user.role) else rules.mask_id_number(guest.id_number)


class LastStaySerializer(serializers.Serializer):
    reservation_id = serializers.UUIDField()
    check_in_date = serializers.DateField()
    room = serializers.CharField()


class GuestListItemSerializer(GuestSerializer):
    """Guest list row (artboard 6.8): history numbers come from ``context["stats"]`` (see ``stats.for_guests``)."""

    stays_count = serializers.SerializerMethodField()
    last_stay = serializers.SerializerMethodField()
    debt = serializers.SerializerMethodField(help_text="Open balance over all stays, minor units.")
    in_house = serializers.SerializerMethodField()

    class Meta(GuestSerializer.Meta):
        fields = [*GuestSerializer.Meta.fields, "stays_count", "last_stay", "debt", "in_house"]

    def get_stays_count(self, guest) -> int:
        return self.context["stats"][guest.pk]["stays_count"]

    @extend_schema_field(LastStaySerializer(allow_null=True))
    def get_last_stay(self, guest):
        return self.context["stats"][guest.pk]["last_stay"]

    def get_debt(self, guest) -> int:
        return self.context["stats"][guest.pk]["debt"]

    def get_in_house(self, guest) -> bool:
        return self.context["stats"][guest.pk]["in_house"]


class GuestHistoryItemSerializer(serializers.Serializer):
    reservation_id = serializers.UUIDField()
    room = serializers.CharField(allow_null=True)
    check_in_date = serializers.DateField()
    check_out_date = serializers.DateField()
    nights = serializers.IntegerField()
    status = serializers.CharField()
    status_label = serializers.CharField()
    balance = serializers.IntegerField()


class GuestWriteSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=120)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    nationality = serializers.CharField(max_length=40, required=False, allow_blank=True)
    id_type = serializers.ChoiceField(choices=IdType.choices, required=False, allow_blank=True)
    id_number = serializers.CharField(max_length=40, required=False, allow_blank=True)
    warning_note = serializers.CharField(max_length=300, required=False, allow_blank=True)
    companions = CompanionSerializer(many=True, required=False)

    def validate_full_name(self, value):
        if len(value.split()) < 2:
            raise serializers.ValidationError("اكتب الاسم الكامل (اسمان على الأقل).")
        return value.strip()

    def validate_phone(self, value):
        if value and not rules.is_valid_phone(value):
            raise serializers.ValidationError("رقم الهاتف غير صحيح.")
        return value


class GuestUpdateSerializer(GuestWriteSerializer):
    version = serializers.IntegerField(min_value=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["full_name"].required = False


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="Image of the ID; compressed on the server to ≤ 300 KB JPEG.")
