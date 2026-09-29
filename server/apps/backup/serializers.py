from rest_framework import serializers

from apps.core.serializers import VersionRequiredMixin

from .models import BackupRun, BackupSettings, ImportRun


class BackupSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackupSettings
        fields = [
            "owner_recipient",
            "interval_hours",
            "keep_count",
            "keep_days",
            "max_total_mb",
            "on_shift_close",
            "auto_drive",
            "second_dir",
            "version",
        ]
        read_only_fields = ["version"]

    def validate_owner_recipient(self, value):
        from . import keys

        if value:
            try:
                keys.recipient(value)
            except Exception:  # noqa: BLE001
                raise serializers.ValidationError("المفتاح العام غير صحيح (يبدأ بـ age1).") from None
        return value.strip()


class BackupSettingsUpdateSerializer(VersionRequiredMixin, BackupSettingsSerializer):
    version = serializers.IntegerField(min_value=1)

    class Meta(BackupSettingsSerializer.Meta):
        read_only_fields = []


class BackupRunSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display")
    status_label = serializers.CharField(source="get_status_display")
    by = serializers.SerializerMethodField()
    uploaded = serializers.SerializerMethodField()

    class Meta:
        model = BackupRun
        fields = [
            "id",
            "created_at",
            "kind",
            "kind_label",
            "status",
            "status_label",
            "seq",
            "full",
            "path",
            "second_path",
            "second_error",
            "size",
            "message",
            "by",
            "uploaded",
        ]

    def get_by(self, run) -> str:
        return run.created_by.full_name if run.created_by_id else "تلقائي"

    def get_uploaded(self, run) -> bool:
        return any(u.ok for u in run.uploads.all())


class ImportCheckSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    detail = serializers.CharField()
    status = serializers.ChoiceField(choices=["ok", "warn", "fail", "run"])


# Why a failed import was refused (spec §9.3: ``upgrade_required`` for a newer schema), from its checks.
IMPORT_CODES = {
    "signature": "corrupt",
    "integrity": "corrupt",
    "hotel": "foreign_hotel",
    "version": "upgrade_required",
    "audit": "audit_chain_broken",
    # 1.1: a format 2 file opened with the owner's or a manager's own login (no local key yet)
    "credentials_required": "credentials_required",
    "credentials_wrong": "credentials_wrong",
}


class ImportRunSerializer(serializers.ModelSerializer):
    by = serializers.CharField(source="created_by.full_name", default=None)
    checks = ImportCheckSerializer(many=True)
    code = serializers.SerializerMethodField(
        help_text="Failed runs: corrupt / foreign_hotel / upgrade_required / audit_chain_broken / older_backup / "
        "credentials_required / credentials_wrong / error",
    )

    class Meta:
        model = ImportRun
        fields = [
            "id",
            "created_at",
            "source",
            "file_name",
            "backup_seq",
            "data_as_of",
            "status",
            "counts",
            "checks",
            "audit_chain_ok",
            "error",
            "code",
            "by",
        ]

    def get_code(self, run) -> str | None:
        if run.status == ImportRun.Status.OK:
            return None
        for check in run.checks or []:
            if check.get("status") == "fail":
                return IMPORT_CODES.get(check.get("key"), "error")
            if check.get("status") == "warn" and check.get("key") == "audit":
                return "older_backup"
        return "error"


class ImportRequestSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="Encrypted backup (.age) from USB or the incoming folder.")
    allow_older = serializers.BooleanField(default=False, help_text="«متابعة رغم ذلك» for an older file.")
    username = serializers.CharField(
        required=False, allow_blank=True, help_text="1.1: the owner's or a manager's login when this PC has no key yet."
    )
    password = serializers.CharField(required=False, allow_blank=True, style={"input_type": "password"})


class AdoptRequestSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="A backup of the hotel (.age).")
    mode = serializers.ChoiceField(
        choices=["view", "work"],
        help_text="view: this PC becomes the owner's read-only copy; work: it replaces a reception PC.",
    )
    username = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(required=False, allow_blank=True, style={"input_type": "password"})


class AdoptResultSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["view", "work"])
    restarting = serializers.BooleanField(help_text="The service restarts within seconds to open the hotel.")


class OwnerStatusSerializer(serializers.Serializer):
    data_as_of = serializers.DateTimeField(allow_null=True)
    last_import = ImportRunSerializer(allow_null=True)
    hours_old = serializers.IntegerField(allow_null=True)
    public_key = serializers.CharField(allow_null=True, help_text="Enter it in the reception's backup settings.")


class DriveStatusSerializer(serializers.Serializer):
    configured = serializers.BooleanField(help_text="client_secret.json installed on this PC")
    linked = serializers.BooleanField()
    email = serializers.CharField(allow_null=True)
    pending_uploads = serializers.IntegerField()
    last_upload_at = serializers.DateTimeField(allow_null=True)


class AuthUrlSerializer(serializers.Serializer):
    url = serializers.URLField()


class SyncResultSerializer(serializers.Serializer):
    uploaded = serializers.IntegerField(help_text="Reception: files uploaded now.")
    downloaded = serializers.ListField(child=serializers.CharField(), help_text="Owner: files fetched to incoming/.")
    message = serializers.CharField()


class CandidateSerializer(serializers.Serializer):
    name = serializers.CharField()
    seq = serializers.IntegerField()
    size = serializers.IntegerField()
    drive_file_id = serializers.CharField(allow_null=True)
    local = serializers.BooleanField()
    state = serializers.ChoiceField(choices=["new", "imported", "older"], help_text="جديدة / مستوردة / أقدم من بياناتك")


class DriveImportSerializer(serializers.Serializer):
    drive_file_id = serializers.CharField(required=False)
    name = serializers.CharField(required=False, help_text="A file already in incoming/.")
    allow_older = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if not attrs.get("drive_file_id") and not attrs.get("name"):
            raise serializers.ValidationError("حدّد ملفًا من Drive أو من مجلد الوارد.")
        return attrs


class UsbDriveSerializer(serializers.Serializer):
    drive = serializers.CharField(help_text="E.g. E:\\")
    label = serializers.CharField(allow_blank=True)
    free = serializers.IntegerField(help_text="Free bytes.")


class UsbCopyRequestSerializer(serializers.Serializer):
    drive = serializers.CharField(max_length=260, help_text="One of GET /backup/usb.")


class UsbCopyResultSerializer(serializers.Serializer):
    folder = serializers.CharField()
    files = serializers.ListField(child=serializers.CharField())
