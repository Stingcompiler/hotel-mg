from rest_framework import serializers

from apps.cash.models import PaymentMethod
from apps.core.fields import MoneyMinorField

from .models import Folio, Payment


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


class PaymentCreateSerializer(serializers.Serializer):
    amount = MoneyMinorField(min_value=1)
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    reference = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")


class RefundSerializer(PaymentCreateSerializer):
    reason = serializers.CharField(max_length=300)


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
        ]
