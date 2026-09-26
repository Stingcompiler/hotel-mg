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
            "id", "full_name", "phone", "nationality", "id_type", "id_number", "warning_note",
            "companions", "documents", "version", "created_at",
        ]  # fmt: skip

    def get_companions(self, guest) -> list[dict]:
        return CompanionSerializer(guest.companions.filter(removed=False), many=True).data

    def get_id_number(self, guest) -> str:
        user = self.context["request"].user
        return guest.id_number if account_rules.is_manager(user.role) else rules.mask_id_number(guest.id_number)


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
