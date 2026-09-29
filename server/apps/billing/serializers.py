from rest_framework import serializers

from apps.cash.models import PaymentMethod
from apps.core.fields import MoneyMinorField
from apps.core.serializers import VersionRequiredMixin

from .models import Currency, Folio, Payment


class FolioTotalsSerializer(serializers.Serializer):
    charges = MoneyMinorField()
    discounts = MoneyMinorField()
    total = MoneyMinorField()
    paid = MoneyMinorField()
    balance = MoneyMinorField(help_text="> 0 the guest owes; < 0 the hotel owes the guest.")


class LedgerEntrySerializer(serializers.Serializer):
    at = serializers.DateTimeField()
    type = serializers.ChoiceField(choices=["line", "payment"])
    id = serializers.UUIDField()
    kind = serializers.CharField()
    text = serializers.CharField()
    debit = MoneyMinorField()
    credit = MoneyMinorField()
    balance = MoneyMinorField()
    reference = serializers.CharField()
    reason = serializers.CharField()
    reverses = serializers.UUIDField(allow_null=True)
    by = serializers.CharField()


class FolioSerializer(serializers.ModelSerializer):
    invoice = serializers.CharField(source="invoice_label", read_only=True)
    reservation = serializers.UUIDField(source="reservation_id", read_only=True)
    guest_name = serializers.CharField(source="reservation.guest.full_name", read_only=True)
    room_number = serializers.CharField(source="reservation.room.number", default=None, read_only=True)
    totals = serializers.SerializerMethodField()
    ledger = serializers.SerializerMethodField()

    class Meta:
        model = Folio
        fields = [
            "id",
            "invoice",
            "invoice_no",
            "reservation",
            "guest_name",
            "room_number",
            "status",
            "totals",
            "ledger",
        ]

    def get_totals(self, folio) -> FolioTotalsSerializer:
        from .services import FolioTotals

        return FolioTotalsSerializer(FolioTotals.of(folio)).data

    def get_ledger(self, folio) -> LedgerEntrySerializer(many=True):
        from .services import ledger

        return LedgerEntrySerializer(ledger(folio), many=True).data


class LineCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[("service", "خدمة"), ("discount", "خصم")])
    description = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    amount = MoneyMinorField(min_value=1, help_text="Always positive; a discount is stored as a credit.")
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    manager_password = serializers.CharField(
        max_length=128, required=False, allow_blank=True, default="", style={"input_type": "password"}
    )
    manager_reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["kind"] == "service" and not attrs["description"].strip():
            raise serializers.ValidationError({"description": "اكتب بيان الخدمة."})
        return attrs


class ReversalSerializer(serializers.Serializer):
    """«عكس» a line or a payment: a reason; the manager's password when the reversal is a price decision (a room
    charge, a discount) or undoes someone else's money (review 2026-09-28, SEC-1)."""

    reason = serializers.CharField(max_length=300)
    manager_password = serializers.CharField(
        max_length=128, required=False, allow_blank=True, default="", style={"input_type": "password"}
    )


class PaymentCreateSerializer(serializers.Serializer):
    amount = MoneyMinorField(min_value=1, required=False, help_text="Base currency; omit when paying in `currency`.")
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    reference = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True, default="", help_text="e.g. USD.")
    foreign_amount = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, help_text="Minor units (cents) of `currency`."
    )

    def validate(self, attrs):
        if attrs.get("currency"):
            if not attrs.get("foreign_amount"):
                raise serializers.ValidationError({"foreign_amount": ["أدخل المبلغ بالعملة المختارة."]})
        elif not attrs.get("amount"):
            raise serializers.ValidationError({"amount": ["هذا الحقل مطلوب."]})
        return attrs


class RefundSerializer(serializers.Serializer):
    amount = MoneyMinorField(min_value=1, required=False, help_text="Base currency; omit when refunding in `currency`.")
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    reference = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    reason = serializers.CharField(max_length=300)
    currency = serializers.CharField(
        max_length=3, required=False, allow_blank=True, default="", help_text="Refund in this currency, e.g. USD."
    )
    foreign_amount = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, help_text="Its minor units."
    )

    def validate(self, attrs):
        if attrs.get("currency") and not attrs.get("foreign_amount"):
            raise serializers.ValidationError({"foreign_amount": ["أدخل المبلغ بالعملة المختارة."]})
        if not attrs.get("currency") and not attrs.get("amount"):
            raise serializers.ValidationError({"amount": ["أدخل المبلغ."]})
        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    receipt = serializers.CharField(source="receipt_label", read_only=True)
    amount = MoneyMinorField(read_only=True)
    by = serializers.CharField(source="created_by.full_name", default=None, read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "receipt",
            "receipt_no",
            "folio",
            "shift",
            "kind",
            "method",
            "amount",
            "reference",
            "reverses",
            "reason",
            "received_at",
            "by",
            "currency",
            "foreign_amount",
            "rate",
        ]


class CurrencySerializer(serializers.ModelSerializer):
    rate = MoneyMinorField(help_text="Base-currency minor units for one whole unit.")

    class Meta:
        model = Currency
        fields = ["id", "code", "name", "symbol", "rate", "is_active", "version", "updated_at"]
        read_only_fields = fields


class CurrencyCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=3, help_text="ISO 4217, e.g. USD.")
    name = serializers.CharField(max_length=40)
    symbol = serializers.CharField(max_length=6, required=False, allow_blank=True, default="")
    rate = MoneyMinorField(min_value=1)


class CurrencyUpdateSerializer(VersionRequiredMixin, serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=40, required=False)
    symbol = serializers.CharField(max_length=6, required=False, allow_blank=True)
    rate = MoneyMinorField(min_value=1, required=False)
    is_active = serializers.BooleanField(required=False)
