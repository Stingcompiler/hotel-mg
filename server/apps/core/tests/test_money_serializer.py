import pytest
from rest_framework import serializers

from apps.core.fields import MoneyMinorField


class AmountSerializer(serializers.Serializer):
    amount = MoneyMinorField()


@pytest.mark.parametrize("value", [0, 1_500_000, -250_000])
def test_accepts_json_integers(value):
    s = AmountSerializer(data={"amount": value})
    assert s.is_valid(), s.errors
    assert s.validated_data["amount"] == value


@pytest.mark.parametrize("value", [150.5, 150.0, "1500", True, None])
def test_rejects_non_integers(value):
    assert not AmountSerializer(data={"amount": value}).is_valid()
