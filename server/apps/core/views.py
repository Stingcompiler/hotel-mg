import shutil

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_field
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsManager, IsOwner
from apps.accounts.services import require_confirmation

from . import rules
from .clock import approve_clock, is_clock_blocked, last_seen_at
from .errors import ApiError
from .fields import MoneyMinorField
from .models import SCHEMA_VERSION, AlertSound, HotelSettings
from .settings_service import reset_alert_sound, set_alert_sound, update_settings


class DefaultLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()
    pin = serializers.CharField()


def _default_login() -> dict | None:
    from apps.accounts import rules as account_rules

    user = User.objects.filter(username=account_rules.DEFAULT_USERNAME, is_active=True, default_password=True).first()
    if user is None:
        return None
    return {
        "username": account_rules.DEFAULT_USERNAME,
        "password": account_rules.DEFAULT_PASSWORD,
        "pin": account_rules.DEFAULT_PIN,
    }


def _backup_opens_elsewhere() -> bool:
    from apps.backup import keyslots  # core must not import backup at module load

    return bool(keyslots.for_export())


def _can_adopt() -> bool:
    from apps.backup.adopt import is_fresh  # core must not import backup at module load

    return is_fresh()


class SystemStatusSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["reception", "owner"])
    hotel_id = serializers.UUIDField(allow_null=True)
    last_backup = serializers.DateTimeField(allow_null=True)
    data_as_of = serializers.DateTimeField(allow_null=True)
    imported_seq = serializers.IntegerField(allow_null=True, help_text="Owner PC: number of the last imported backup.")
    device_name = serializers.CharField(help_text="This PC's name (login footer).")
    backup_stale_hours = serializers.IntegerField(
        allow_null=True, help_text="Hours since the last backup once past the «no backup» alert threshold."
    )
    clock_blocked = serializers.BooleanField()
    clock_last_seen_at = serializers.DateTimeField(allow_null=True, help_text="Latest recorded write on this PC.")
    disk_free_bytes = serializers.IntegerField(allow_null=True, help_text="Free space on the data disk.")
    disk_low = serializers.BooleanField(help_text="Free space under the backup safety margin (system bar).")
    needs_setup = serializers.BooleanField(
        help_text="Reception PC with no users yet: the login page creates the manager."
    )
    due_tasks = serializers.IntegerField(
        allow_null=True,
        help_text="Reception PC: open follow-up tasks due now (login chip «N مهام متابعة مستحقة»); a count only.",
    )
    owner_public_key = serializers.CharField(
        allow_null=True, help_text="Owner PC: public key to paste in the reception's backup settings (public)."
    )
    backup_opens_elsewhere = serializers.BooleanField(
        allow_null=True,
        help_text="Reception PC: new backups carry a key slot (an owner/manager changed the default password), so "
        "they open on another PC. False = they open only here (the system bar warns). Owner PC: null.",
    )
    can_adopt = serializers.BooleanField(
        help_text="1.1: a new PC (only the untouched default account): «استيراد نسخة» may open a hotel here."
    )
    default_login = DefaultLoginSerializer(
        allow_null=True,
        help_text="The install's default owner account while its password is unchanged (the login page shows it).",
    )
    version = serializers.CharField()
    schema_version = serializers.IntegerField()
    spa_built = serializers.BooleanField(help_text="static_spa/index.html is present next to this server (support).")


def _due_tasks() -> int:
    """Open tasks due by now — a number for the login chip, never the tasks themselves (design gap #13)."""
    from apps.followups import rules as followup_rules
    from apps.followups.models import FollowupTask

    # The same number as the bell badge (`followups/tasks/count`), so the chip and the badge never disagree.
    return FollowupTask.objects.filter(status__in=followup_rules.OPEN_STATES).count()


def _owner_public_key() -> str | None:
    from apps.backup import keys

    return str(keys.load().to_public()) if keys.identity_path().exists() else None


def _disk_free(path) -> int | None:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None


class SystemStatusView(APIView):
    """Read before login: the SPA picks the reception or owner shell from ``role`` (spec §10.4)."""

    permission_classes = [AllowAny]

    @extend_schema(responses=SystemStatusSerializer)
    def get(self, request):
        from apps.backup import rules as backup_rules  # core must not import backup at module load
        from apps.backup.export import last_backup_at
        from apps.backup.merge import last_imported
        from apps.followups.models import AlertRule, TriggerKind

        last_import = last_imported() if settings.SKYTOWERS_ROLE == "owner" else None
        free = _disk_free(settings.RUNTIME.home)
        last_backup = last_backup_at()
        rule = AlertRule.objects.filter(trigger_kind=TriggerKind.NO_BACKUP, is_active=True).first()
        limit = (rule.threshold_hours if rule else None) or 24
        data = {
            "role": settings.SKYTOWERS_ROLE,
            "hotel_id": settings.RUNTIME.hotel_id,
            "last_backup": last_backup,
            "backup_stale_hours": backup_rules.stale_hours(last_backup, timezone.now(), limit),
            "data_as_of": last_import.data_as_of if last_import else None,
            "imported_seq": last_import.backup_seq if last_import else None,
            "device_name": settings.RUNTIME.device_name,
            "clock_blocked": is_clock_blocked(),
            "clock_last_seen_at": last_seen_at(),
            "disk_free_bytes": free,
            "disk_low": rules.disk_low(free),
            "needs_setup": settings.SKYTOWERS_ROLE == "reception" and not User.objects.exists(),
            "due_tasks": _due_tasks() if settings.SKYTOWERS_ROLE == "reception" else None,
            "owner_public_key": _owner_public_key() if settings.SKYTOWERS_ROLE == "owner" else None,
            "default_login": _default_login() if settings.SKYTOWERS_ROLE == "reception" else None,
            "can_adopt": _can_adopt(),
            "backup_opens_elsewhere": _backup_opens_elsewhere() if settings.SKYTOWERS_ROLE == "reception" else None,
            "version": settings.APP_VERSION,
            "schema_version": SCHEMA_VERSION,
            "spa_built": (settings.SPA_ROOT / "index.html").is_file(),
        }
        return Response(SystemStatusSerializer(data).data)


class ClockApproveView(APIView):
    """Manager accepts the device clock after a rollback block (spec §6.7). Needs X-Confirm-Token."""

    permission_classes = [IsManager]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        require_confirmation(request)
        approve_clock(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AlertSoundInfoSerializer(serializers.Serializer):
    name = serializers.CharField()
    updated_at = serializers.DateTimeField()


class HotelSettingsSerializer(serializers.ModelSerializer):
    alert_sound = serializers.SerializerMethodField(
        help_text="The owner's alert sound {name, updated_at}; null: the app's built-in tone."
    )

    @extend_schema_field(AlertSoundInfoSerializer(allow_null=True))
    def get_alert_sound(self, obj):
        sound = AlertSound.objects.filter(hotel_id=obj.hotel_id).only("name", "updated_at", "content_type").first()
        if sound is None or not sound.content_type:
            return None
        return {"name": sound.name, "updated_at": sound.updated_at}

    expense_attachment_threshold = MoneyMinorField(min_value=0)
    debt_attention_threshold = MoneyMinorField(min_value=0, required=False)

    class Meta:
        model = HotelSettings
        fields = [
            "name_ar",
            "name_latin",
            "address",
            "phone",
            "currency",
            "digits",
            "money_decimals",
            "stay_day_end",
            "session_lock_minutes",
            "expense_attachment_threshold",
            "max_discount_percent",
            "debt_attention_threshold",
            "auto_print_receipt",
            "thermal_printer",
            "hotel_id",
            "alert_sound",
            "version",
            "updated_at",
        ]
        read_only_fields = ["currency", "hotel_id", "alert_sound", "version", "updated_at"]


class HotelSettingsUpdateSerializer(HotelSettingsSerializer):
    version = serializers.IntegerField(min_value=1)

    class Meta(HotelSettingsSerializer.Meta):
        read_only_fields = ["currency", "hotel_id", "updated_at"]

    def validate(self, attrs):
        if "version" not in attrs:  # partial=True would otherwise let it through
            raise serializers.ValidationError({"version": ["هذا الحقل مطلوب."]})
        return attrs


class HotelSettingsView(APIView):
    """Settings → بيانات الفندق (V2 artboard 6.11 D). Anyone signed in reads (digits, names on prints)."""

    def get_permissions(self):
        return [IsManager()] if self.request.method == "PATCH" else [IsAuthenticated()]

    @extend_schema(responses=HotelSettingsSerializer)
    def get(self, request):
        return Response(HotelSettingsSerializer(HotelSettings.load()).data)

    @extend_schema(request=HotelSettingsUpdateSerializer, responses=HotelSettingsSerializer)
    def patch(self, request):
        data = HotelSettingsUpdateSerializer(HotelSettings.load(), data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        return Response(HotelSettingsSerializer(update_settings(request.user, **data.validated_data)).data)


class AlertSoundUploadSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="MP3, WAV or OGG up to 1 MB.")


class AlertSoundView(APIView):
    """The alert sound: everyone signed in plays it (404: use the built-in tone); only the owner changes it."""

    parser_classes = [MultiPartParser]

    def get_permissions(self):
        return [IsAuthenticated()] if self.request.method == "GET" else [IsOwner()]

    @extend_schema(responses={(200, "audio/mpeg"): OpenApiResponse(OpenApiTypes.BINARY), 404: None})
    def get(self, request):
        sound = AlertSound.objects.filter(hotel_id=HotelSettings.load().hotel_id).first()
        if sound is None or not sound.data:
            raise ApiError("not_found", 404, detail="لا يوجد صوت مختار — يُستخدم الصوت الافتراضي.")
        return HttpResponse(bytes(sound.data), content_type=sound.content_type)

    @extend_schema(request=AlertSoundUploadSerializer, responses={204: None})
    def post(self, request):
        data = AlertSoundUploadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        upload = data.validated_data["file"]
        set_alert_sound(request.user, name=upload.name, raw=upload.read())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses={204: None})
    def delete(self, request):
        reset_alert_sound(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
