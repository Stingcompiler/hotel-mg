from rest_framework import serializers

from .models import BackupRun, BackupSettings, ImportRun


class BackupSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackupSettings
        fields = [
            "owner_recipient",
            "interval_hours",
            "keep_count",
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


class BackupSettingsUpdateSerializer(BackupSettingsSerializer):
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


class ImportRunSerializer(serializers.ModelSerializer):
    by = serializers.CharField(source="created_by.full_name", default=None)
    checks = ImportCheckSerializer(many=True)

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
            "by",
        ]


class ImportRequestSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="Encrypted backup (.age) from USB or the incoming folder.")
    allow_older = serializers.BooleanField(default=False, help_text="«متابعة رغم ذلك» for an older file.")


class OwnerStatusSerializer(serializers.Serializer):
    data_as_of = serializers.DateTimeField(allow_null=True)
    last_import = ImportRunSerializer(allow_null=True)
    hours_old = serializers.IntegerField(allow_null=True)
    public_key = serializers.CharField(allow_null=True, help_text="Enter it in the reception's backup settings.")
