"""Response shapes of the print-document endpoints (artboards 7.1–7.3), typed for the generated client.

Money in minor units. The SPA renders the templates; these are the facts it prints.
"""

from rest_framework import serializers

from apps.billing.serializers import LedgerEntrySerializer
from apps.cash.serializers import MethodTotalsSerializer, MovementSerializer
from apps.core.fields import MoneyMinorField
from apps.core.models import HotelSettings

Text = serializers.CharField


class HotelHeaderSerializer(serializers.Serializer):
    name_ar = Text()
    name_latin = Text()
    address = Text()
    phone = Text()
    digits = serializers.ChoiceField(choices=HotelSettings.Digits.choices)
    money_decimals = serializers.IntegerField()


class InvoiceGuestSerializer(serializers.Serializer):
    name = Text()
    phone = Text()
    id_type = Text()
    id_number = Text()
    companions = serializers.ListField(child=Text())


class InvoiceStaySerializer(serializers.Serializer):
    room = Text(allow_null=True)
    room_type = Text()
    duration_kind = Text(help_text="Arabic label: يومي / أسبوعي / شهري / مختلط.")
    check_in_date = serializers.DateField()
    last_night = serializers.DateField()
    nights = serializers.IntegerField()
    state = Text()


class InvoiceTotalsSerializer(serializers.Serializer):
    charges = MoneyMinorField(help_text="Before the discount.")
    discount = MoneyMinorField(help_text="Positive amount taken off.")
    total = MoneyMinorField()
    paid = MoneyMinorField()
    balance = MoneyMinorField()


class InvoiceItemSerializer(serializers.Serializer):
    at = serializers.DateTimeField()
    kind = Text()
    text = Text()
    quantity = serializers.IntegerField()
    unit_price = MoneyMinorField()
    total = MoneyMinorField()


class InvoicePaymentSerializer(serializers.Serializer):
    at = serializers.DateTimeField()
    receipt = Text()
    kind = Text()
    method = Text()
    reference = Text()
    amount = MoneyMinorField()


class InvoiceDocumentSerializer(serializers.Serializer):
    hotel = HotelHeaderSerializer()
    invoice = Text()
    printed_at = serializers.DateTimeField()
    printed_by = Text()
    guest = InvoiceGuestSerializer()
    stay = InvoiceStaySerializer()
    ledger = LedgerEntrySerializer(many=True)
    items = InvoiceItemSerializer(many=True, help_text="Charges net of reversals (artboard 7.1 table).")
    payments = InvoicePaymentSerializer(many=True)
    totals = InvoiceTotalsSerializer()
    notes = serializers.ListField(child=Text())


class PaymentReceiptDocumentSerializer(serializers.Serializer):
    hotel = HotelHeaderSerializer()
    receipt = Text()
    kind = Text()
    at = serializers.DateTimeField()
    room = Text(allow_null=True)
    guest = Text()
    invoice = Text()
    check_in_date = serializers.DateField()
    last_night = serializers.DateField()
    nights = serializers.IntegerField()
    amount = MoneyMinorField()
    amount_in_words = Text()
    paid_in = Text(allow_null=True, help_text="«150 $ بسعر 2,500» when paid in another currency.")
    method = Text()
    reference = Text()
    stay_total = MoneyMinorField()
    paid_to_date = MoneyMinorField()
    balance = MoneyMinorField()
    by = Text()
    shift = Text()


class ExpenseReceiptDocumentSerializer(serializers.Serializer):
    hotel = HotelHeaderSerializer()
    number = Text()
    at = serializers.DateTimeField()
    category = Text()
    note = Text()
    room = Text(allow_null=True)
    amount = MoneyMinorField()
    amount_in_words = Text()
    method = Text()
    by = Text()


class StatementShiftSerializer(serializers.Serializer):
    id = Text()
    device = Text()
    opened_at = serializers.DateTimeField()
    closed_at = serializers.DateTimeField(allow_null=True)
    opened_by = Text()
    closed_by = Text()


class StatementTilesSerializer(serializers.Serializer):
    opening = MoneyMinorField()
    receipts = MethodTotalsSerializer()
    cash_expenses = MoneyMinorField()
    expected = MoneyMinorField()


class ShiftStatementDocumentSerializer(serializers.Serializer):
    hotel = HotelHeaderSerializer()
    shift = StatementShiftSerializer()
    printed_at = serializers.DateTimeField()
    printed_by = Text()
    tiles = StatementTilesSerializer()
    movements = MovementSerializer(many=True)
    counted = MoneyMinorField(allow_null=True)
    difference = MoneyMinorField(allow_null=True)
    difference_reason = Text()
    formula = Text()
