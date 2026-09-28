from rest_framework import serializers

from apps.core.fields import MoneyMinorField
from apps.core.serializers import VersionRequiredMixin
from apps.stays.serializers import AFTER_ROOM_STATUS, BOOKING_KINDS

from .models import AlertRule, TaskAction, Toast, TriggerKind


class StayInfoMixin(serializers.Serializer):
    stay = serializers.UUIDField(allow_null=True)
    room = serializers.CharField(allow_null=True)
    room_state = serializers.CharField(required=False)
    guest = serializers.CharField(required=False)
    kind = serializers.CharField(required=False)
    last_night = serializers.DateField(required=False)
    when = serializers.CharField(required=False, help_text="«تنتهي بعد يومين», «متجاوزة منذ يوم»")


class TaskRowSerializer(StayInfoMixin):
    id = serializers.UUIDField()
    rule = serializers.CharField(help_text="«قاعدة: شهري – قبل 5 أيام · 09:00»")
    trigger_kind = serializers.ChoiceField(choices=TriggerKind.choices)
    title = serializers.CharField()
    status = serializers.CharField()
    due_at = serializers.DateTimeField()
    snooze_count = serializers.IntegerField()
    max_snoozes = serializers.IntegerField()
    snooze_label = serializers.CharField(help_text="«تأجيل (2 من 3)»")
    can_snooze = serializers.BooleanField()
    next_at = serializers.DateTimeField(allow_null=True)
    note = serializers.CharField()
    neglected_shift_user = serializers.CharField(allow_null=True, help_text="«مُهمَلة — وردية: أحمد»")
    version = serializers.IntegerField()


class UpcomingRowSerializer(StayInfoMixin):
    rule = serializers.CharField()
    alert_at = serializers.DateTimeField(help_text="«سيُنبَّه الجمعة 9 أكتوبر 09:00»")


class CountsSerializer(serializers.Serializer):
    late = serializers.IntegerField()
    today = serializers.IntegerField()
    upcoming = serializers.IntegerField()
    system = serializers.IntegerField()


class TaskCountSerializer(CountsSerializer):
    count = serializers.IntegerField(help_text="Open tasks (open, snoozed, waiting, neglected): the badge number.")


class LastActionSerializer(serializers.Serializer):
    text = serializers.CharField()
    by = serializers.CharField()
    at = serializers.DateTimeField()


class BoardSerializer(serializers.Serializer):
    counts = CountsSerializer()
    late = TaskRowSerializer(many=True)
    today = TaskRowSerializer(many=True)
    upcoming = UpcomingRowSerializer(many=True)
    system = TaskRowSerializer(many=True)
    last_action = LastActionSerializer(allow_null=True)


class StayActionParamsSerializer(serializers.Serializer):
    """extend: duration_kind, count, option_key…; confirm_checkout: room_status, override_password…"""

    duration_kind = serializers.ChoiceField(choices=BOOKING_KINDS, required=False)
    count = serializers.IntegerField(min_value=1, max_value=366, required=False)
    option_key = serializers.CharField(required=False, allow_null=True)
    final_total = MoneyMinorField(required=False, allow_null=True, min_value=1)
    override_reason = serializers.CharField(max_length=300, required=False, allow_blank=True)
    room_status = serializers.ChoiceField(choices=AFTER_ROOM_STATUS, required=False)
    maintenance_reason = serializers.CharField(max_length=200, required=False, allow_blank=True)
    override_password = serializers.CharField(
        max_length=128, required=False, allow_blank=True, style={"input_type": "password"}
    )


class ActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=TaskAction.Action.choices)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    until = serializers.DateTimeField(required=False, allow_null=True, help_text="snooze / waiting: when it returns")
    version = serializers.IntegerField(min_value=1, required=False)
    stay = StayActionParamsSerializer(required=False, help_text="Parameters for extend / confirm_checkout.")

    def validate(self, attrs):
        if attrs["action"] == "extend":
            params = attrs.get("stay") or {}
            if not params.get("duration_kind") or not params.get("count"):
                raise serializers.ValidationError({"stay": "حدّد نوع المدة والعدد للتمديد."})
        return attrs


class TaskActionSerializer(serializers.ModelSerializer):
    by = serializers.CharField(source="created_by.full_name", default=None)
    label = serializers.CharField(source="get_action_display")

    class Meta:
        model = TaskAction
        fields = ["id", "action", "label", "at", "note", "next_at", "by"]


class ToastSerializer(serializers.ModelSerializer):
    task = serializers.UUIDField(source="task_id")

    class Meta:
        model = Toast
        fields = ["seq", "task", "title", "body", "at"]


class ToastBatchSerializer(serializers.Serializer):
    cursor = serializers.IntegerField(help_text="Pass back as ?after= on the next poll.")
    toasts = ToastSerializer(many=True)


class AlertRuleSerializer(serializers.ModelSerializer):
    threshold = MoneyMinorField(required=False, allow_null=True, min_value=0)

    class Meta:
        model = AlertRule
        fields = [
            "id",
            "name",
            "trigger_kind",
            "duration_kind",
            "days_before",
            "second_days_before",
            "at_time",
            "repeat_hours",
            "max_snoozes",
            "escalate_after_hours",
            "threshold_hours",
            "threshold",
            "windows_notification",
            "is_active",
            "version",
        ]
        read_only_fields = ["id", "version"]


class AlertRuleUpdateSerializer(VersionRequiredMixin, AlertRuleSerializer):
    version = serializers.IntegerField(min_value=1)

    class Meta(AlertRuleSerializer.Meta):
        read_only_fields = ["id"]


class PreviewRequestSerializer(serializers.Serializer):
    last_night = serializers.DateField()
    duration_kind = serializers.ChoiceField(choices=BOOKING_KINDS, required=False)
    days_before = serializers.IntegerField(min_value=0, max_value=60, default=0)
    second_days_before = serializers.IntegerField(min_value=0, max_value=60, required=False, allow_null=True)
    at_time = serializers.TimeField(required=False)
    repeat_hours = serializers.IntegerField(min_value=0, max_value=168, default=0)


class PreviewStaySerializer(serializers.Serializer):
    room = serializers.CharField()
    guest = serializers.CharField()
    last_night = serializers.DateField()


class PreviewSerializer(serializers.Serializer):
    last_night = serializers.DateField()
    first_at = serializers.DateTimeField()
    second_at = serializers.DateTimeField(allow_null=True)
    repeat_hours = serializers.IntegerField()
    affected_stays = serializers.IntegerField()
    stays = PreviewStaySerializer(many=True, help_text="Up to eight of the affected stays, soonest ending first.")
