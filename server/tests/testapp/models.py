"""Concrete models for testing the abstract core bases. Installed only in test settings."""

from django.db import models

from apps.core.fields import MoneyField
from apps.core.models import AppendOnlyModel, BaseModel


class Priced(BaseModel):
    name = models.CharField(max_length=40)
    price = MoneyField()


class Ledger(AppendOnlyModel):
    amount = MoneyField()
