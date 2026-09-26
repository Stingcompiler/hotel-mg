from rest_framework import serializers

from apps.core.fields import MoneyMinorField
from apps.rooms.models import Room

from .models import Expense, ExpenseCategory, PaymentMethod, Shift


class MethodTotalsSerializer(serializers.Serializer):
    cash = MoneyMinorField()
    bankak = MoneyMinorField()
    transfer = MoneyMinorField()
    total = MoneyMinorField()


class ShiftSerializer(serializers.ModelSerializer):
    opened_by = serializers.CharField(source="created_by.full_name", default=None, read_only=True)
    closed_by_name = serializers.CharField(source="closed_by.full_name", default=None, read_only=True)
    opening = MoneyMinorField(read_only=True)
    expected = MoneyMinorField(read_only=True, allow_null=True)
    counted = MoneyMinorField(read_only=True, allow_null=True)
    difference = MoneyMinorField(read_only=True, allow_null=True)

    class Meta:
        model = Shift
        fields = [
            "id",
            "device",
            "opened_at",
            "opened_by",
            "opening",
            "closed_at",
            "closed_by_name",
            "expected",
            "counted",
            "difference",
            "difference_reason",
            "version",
        ]


class ShiftTotalsSerializer(serializers.Serializer):
    opening = MoneyMinorField()
    receipts = MethodTotalsSerializer()
    expenses = MethodTotalsSerializer()
    expected = MoneyMinorField(help_text="Opening + cash receipts − cash expenses.")


class MovementSerializer(serializers.Serializer):
    at = serializers.DateTimeField()
    kind = serializers.ChoiceField(choices=["open", "in", "out"])
    text = serializers.CharField()
    amount = MoneyMinorField(help_text="Signed: money out is negative.")
    method = serializers.CharField()
    reference = serializers.CharField()
    by = serializers.CharField()
    ref_id = serializers.CharField()


class ShiftDetailSerializer(serializers.Serializer):
    shift = ShiftSerializer()
    totals = ShiftTotalsSerializer()
    movements = MovementSerializer(many=True)


class CurrentShiftSerializer(serializers.Serializer):
    shift = ShiftSerializer(allow_null=True)
    totals = ShiftTotalsSerializer(allow_null=True)
    movements = MovementSerializer(many=True)
    last_closed = ShiftSerializer(allow_null=True)
    suggested_opening = MoneyMinorField()


class OpenShiftSerializer(serializers.Serializer):
    opening = MoneyMinorField(min_value=0)


class CloseShiftSerializer(serializers.Serializer):
    counted = MoneyMinorField(min_value=0)
    difference_reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    version = serializers.IntegerField(min_value=1, required=False)


class ShiftHistoryRowSerializer(ShiftSerializer):
    receipts = MoneyMinorField(read_only=True, help_text="Cash receipts.")
    cash_expenses = MoneyMinorField(read_only=True)

    class Meta(ShiftSerializer.Meta):
        fields = [*ShiftSerializer.Meta.fields, "receipts", "cash_expenses"]


class ShiftHistorySerializer(serializers.Serializer):
    count = serializers.IntegerField()
    with_difference = serializers.IntegerField()
    net_difference = MoneyMinorField()
    shifts = ShiftHistoryRowSerializer(many=True)


class ExpenseSerializer(serializers.ModelSerializer):
    amount = MoneyMinorField(read_only=True)
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    by = serializers.CharField(source="created_by.full_name", default=None, read_only=True)
    room_number = serializers.CharField(source="room.number", default=None, read_only=True)
    attachments = serializers.SerializerMethodField()
    attachment_missing = serializers.SerializerMethodField()
    reversed = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = [
            "id",
            "shift",
            "category",
            "category_label",
            "amount",
            "note",
            "method",
            "reference",
            "room",
            "room_number",
            "spent_at",
            "reverses",
            "reason",
            "reversed",
            "attachments",
            "attachment_missing",
            "by",
        ]

    def get_attachments(self, expense) -> list[str]:
        return [str(a.pk) for a in expense.attachments.all()]

    def get_attachment_missing(self, expense) -> bool:
        from . import rules

        return rules.attachment_missing(expense.amount, self.context["threshold"], bool(self.get_attachments(expense)))

    def get_reversed(self, expense) -> bool:
        return hasattr(expense, "reversed_by")


class ExpenseCreateSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=ExpenseCategory.choices)
    amount = MoneyMinorField(min_value=1)
    note = serializers.CharField(max_length=300)
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    reference = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all(), required=False, allow_null=True)


class ExpenseSummarySerializer(serializers.Serializer):
    shift_total = MoneyMinorField()
    shift_count = serializers.IntegerField()
    month_total = MoneyMinorField()
    top_category = serializers.CharField(allow_null=True)
    top_category_total = MoneyMinorField()
    awaiting_attachment = serializers.IntegerField()


class UploadSerializer(serializers.Serializer):
    file = serializers.FileField()
