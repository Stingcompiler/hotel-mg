import uuid
from decimal import Decimal

import pytest
from django.conf import settings
from django.db import transaction

from apps.core.concurrency import get_for_update
from apps.core.errors import VersionConflict
from apps.core.models import AppendOnlyError
from tests.testapp.models import Ledger, Priced

pytestmark = pytest.mark.django_db


def test_base_model_defaults():
    row = Priced.objects.create(name="a", price=1_500_000)
    assert isinstance(row.id, uuid.UUID)
    assert row.hotel_id == settings.RUNTIME.hotel_id
    assert row.version == 1
    assert row.created_at is not None and row.updated_at is not None


def test_version_increments_on_every_save():
    row = Priced.objects.create(name="a", price=100)
    row.name = "b"
    row.save()
    assert row.version == 2
    row.price = 200
    row.save(update_fields=["price"])
    row.refresh_from_db()
    assert row.version == 3
    assert row.price == 200


def test_money_field_rejects_floats_and_decimals():
    for bad in (15000.0, Decimal("150.00"), True):
        with pytest.raises(TypeError):
            Priced.objects.create(name="bad", price=bad)


def test_money_field_stores_large_signed_minor_units():
    row = Priced.objects.create(name="big", price=-9_000_000_000_000)
    row.refresh_from_db()
    assert row.price == -9_000_000_000_000


def test_get_for_update_detects_stale_version():
    row = Priced.objects.create(name="a", price=100)
    with transaction.atomic():
        assert get_for_update(Priced.objects, row.pk, expected_version=1).pk == row.pk
    with pytest.raises(VersionConflict), transaction.atomic():
        get_for_update(Priced.objects, row.pk, expected_version=7)


@pytest.mark.django_db(transaction=True)  # no wrapping test transaction
def test_get_for_update_requires_transaction():
    row = Priced.objects.create(name="a", price=100)
    with pytest.raises(RuntimeError):
        get_for_update(Priced.objects, row.pk, expected_version=None)


def test_append_only_blocks_update_and_delete():
    line = Ledger.objects.create(amount=500)
    line.amount = 600
    with pytest.raises(AppendOnlyError):
        line.save()
    with pytest.raises(AppendOnlyError):
        line.delete()
    with pytest.raises(AppendOnlyError):
        Ledger.objects.filter(pk=line.pk).update(amount=1)
    with pytest.raises(AppendOnlyError):
        Ledger.objects.all().delete()
    Ledger.objects.create(amount=-500)  # corrections are new rows
    assert sorted(Ledger.objects.values_list("amount", flat=True)) == [-500, 500]
