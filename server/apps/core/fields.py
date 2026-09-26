"""Money is stored as signed integers in minor units (piasters, x100). Never floats (spec §5)."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from rest_framework import serializers


def _require_int(value):
    # bool is an int subclass; True/False are never amounts.
    if isinstance(value, bool) or isinstance(value, (float, Decimal)):
        raise TypeError(f"Money must be an int in minor units, got {type(value).__name__}: {value!r}")
    return value


class MoneyField(models.BigIntegerField):
    """Signed amount in minor units. Rejects float/Decimal so rounding bugs cannot slip in."""

    description = "Money amount in minor units (piasters)"

    def get_prep_value(self, value):
        if value is None:
            return None
        return super().get_prep_value(_require_int(value))

    def to_python(self, value):
        if isinstance(value, (float, Decimal)) and not isinstance(value, bool):
            raise ValidationError("المبلغ يجب أن يكون عددًا صحيحًا بالقروش.", code="invalid_money")
        return super().to_python(value)


class MoneyMinorField(serializers.IntegerField):
    """API counterpart of MoneyField: accepts only JSON integers (no floats, no numeric strings)."""

    default_error_messages = {
        "invalid": "المبلغ يجب أن يكون عددًا صحيحًا بالقروش.",
    }

    def to_internal_value(self, data):
        if isinstance(data, bool) or not isinstance(data, int):
            self.fail("invalid")
        return super().to_internal_value(data)
