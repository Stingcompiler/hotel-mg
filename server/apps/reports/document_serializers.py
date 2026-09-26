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
    total = MoneyMinorField()
    paid = MoneyMinorField()
    balance = MoneyMinorField()


class InvoiceDocumentSerializer(serializers.Serializer):
    hotel = HotelHeaderSerializer()
    invoice = Text()
    printed_at = serializers.DateTimeField()
    printed_by = Text()
    guest = InvoiceGuestSerializer()
    stay = InvoiceStaySerializer()
    ledger = LedgerEntrySerializer(many=True)
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
    amount = MoneyMinorField()
    amount_in_words = Text()
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
