from django.db import transaction

from apps.audit import services as audit

from .concurrency import get_for_update
from .models import HotelSettings


@transaction.atomic
def update_settings(actor, *, version: int, **changes) -> HotelSettings:
    current = HotelSettings.load()
    settings_row = get_for_update(HotelSettings.objects, current.pk, version)
    before = audit.snapshot(settings_row)
    for field, value in changes.items():
        setattr(settings_row, field, value)
    settings_row.save()
    audit.record(
        actor=actor,
        action="settings.update",
        entity="hotel_settings",
        entity_id=settings_row.pk,
        before=before,
        after=audit.snapshot(settings_row),
    )
    return settings_row
