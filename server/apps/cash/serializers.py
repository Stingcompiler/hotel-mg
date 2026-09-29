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
    opening_expected = MoneyMinorField(read_only=True, allow_null=True, help_text="Left by the previous shift.")
    handed_over = MoneyMinorField(read_only=True, help_text="Pounds handed to the owner at close.")
    opening_foreign = serializers.DictField(child=serializers.IntegerField(), read_only=True)
    expected_foreign = serializers.DictField(child=serializers.IntegerField(), read_only=True)
    counted_foreign = serializers.DictField(child=serializers.IntegerField(), read_only=True)
    handed_over_foreign = serializers.DictField(child=serializers.IntegerField(), read_only=True)

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
            "opening_expected",
            "opening_reason",
            "handed_over",
            "opening_foreign",
            "expected_foreign",
            "counted_foreign",
            "handed_over_foreign",
            "version",
        ]


class ForeignTotalSerializer(serializers.Serializer):
    currency = serializers.CharField(help_text="ISO code, e.g. USD.")
    symbol = serializers.CharField()
    cash = serializers.IntegerField(help_text="Cash of this currency in the drawer, in its minor units (cents).")
    total = serializers.IntegerField(help_text="Every method, in its minor units.")
    base = MoneyMinorField(help_text="Base-currency equivalent at the rates used.")
    opening = serializers.IntegerField(help_text="In the drawer at opening, its minor units.")
    expected = serializers.IntegerField(help_text="Opening + cash received − cash refunded, its minor units.")


class ShiftTotalsSerializer(serializers.Serializer):
    opening = MoneyMinorField()
    receipts = MethodTotalsSerializer(help_text="Base-currency payments only.")
    expenses = MethodTotalsSerializer()
    expected = MoneyMinorField(help_text="Opening + cash receipts − cash expenses (pounds in the drawer).")
    foreign = ForeignTotalSerializer(many=True, help_text="Received in other currencies; not part of «expected».")


class MovementSerializer(serializers.Serializer):
    at = serializers.DateTimeField()
    kind = serializers.ChoiceField(choices=["open", "in", "out", "handover"])
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
    suggested_opening = MoneyMinorField(help_text="Left in the drawer by the last shift (counted − handed over).")
    suggested_opening_foreign = serializers.DictField(
        child=serializers.IntegerField(), help_text="Foreign cash left by the last shift: code → its minor units."
    )


def foreign_cash(**extra) -> serializers.DictField:
    """Foreign cash: currency code → its minor units (a new child field per use: DRF binds it)."""
    return serializers.DictField(child=serializers.IntegerField(min_value=0), required=False, default=dict, **extra)


class OpenShiftSerializer(serializers.Serializer):
    opening = MoneyMinorField(min_value=0)
    opening_foreign = foreign_cash(help_text="Foreign cash in the drawer: code → minor units.")
    opening_reason = serializers.CharField(
        max_length=300,
        required=False,
        allow_blank=True,
        default="",
        help_text="Required when it differs from what was left.",
    )


class CloseShiftSerializer(serializers.Serializer):
    counted = MoneyMinorField(min_value=0)
    counted_foreign = foreign_cash(help_text="Foreign cash counted: code → minor units.")
    handed_over = MoneyMinorField(min_value=0, required=False, default=0, help_text="Pounds taken out for the owner.")
    handed_over_foreign = foreign_cash()
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


class ExpenseReversalSerializer(serializers.Serializer):
    """«عكس مصروف»: a reason; the manager's password when it is someone else's expense or from a closed shift."""

    reason = serializers.CharField(max_length=300)
    manager_password = serializers.CharField(
        max_length=128, required=False, allow_blank=True, default="", style={"input_type": "password"}
    )
