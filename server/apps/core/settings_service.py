from django.db import transaction

from apps.audit import services as audit

from .concurrency import get_for_update
from .errors import ApiError
from .models import AlertSound, HotelSettings
from .rules import ALERT_SOUND_MAX_BYTES, sound_type


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


@transaction.atomic
def set_alert_sound(actor, *, name: str, raw: bytes) -> AlertSound:
    """The owner's own alert sound: MP3, WAV or OGG up to 1 MB."""
    if len(raw) > ALERT_SOUND_MAX_BYTES:
        raise ApiError("validation_error", 400, detail="ملف الصوت أكبر من 1 ميغابايت.")
    content_type = sound_type(raw)
    if content_type is None:
        raise ApiError("validation_error", 400, detail="اختر ملف صوت MP3 أو WAV أو OGG.")
    sound = AlertSound.load()
    sound.name, sound.content_type, sound.data = name[:120], content_type, raw
    sound.save()
    audit.record(
        actor=actor,
        action="settings.alert_sound",
        entity="alert_sound",
        entity_id=sound.pk,
        after={"name": sound.name, "content_type": content_type, "bytes": len(raw)},
    )
    return sound


@transaction.atomic
def reset_alert_sound(actor) -> AlertSound:
    """Back to the built-in tone."""
    sound = AlertSound.load()
    before = {"name": sound.name}
    sound.name, sound.content_type, sound.data = "", "", None
    sound.save()
    audit.record(
        actor=actor, action="settings.alert_sound_reset", entity="alert_sound", entity_id=sound.pk, before=before
    )
    return sound
