from uuid import uuid4

from django.db import models
from django.utils import timezone

from .fields import MoneyField
from .hotel import current_hotel_id

# Bumped whenever a migration changes the data a backup carries (spec §9.1 manifest).
SCHEMA_VERSION = 1


class BaseModel(models.Model):
    """Common fields for every hotel record (spec §5).

    UUID keys and ``updated_at`` make additive merge import possible (spec §9.3).
    ``version`` is incremented on every save and checked on PUT/PATCH (spec §7).
    """

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    hotel_id = models.UUIDField(db_index=True, default=current_hotel_id)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            self.version += 1
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "version", "updated_at"}
        super().save(*args, **kwargs)


class AppendOnlyError(Exception):
    pass


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise AppendOnlyError(f"{self.model.__name__} is append-only; record a correcting row instead.")

    def delete(self):
        raise AppendOnlyError(f"{self.model.__name__} is append-only; rows are never deleted.")


class AppendOnlyModel(BaseModel):
    """Rows are inserted once and never updated or deleted; corrections are new rows (spec §5)."""

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyError(f"{type(self).__name__} is append-only; record a correcting row instead.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError(f"{type(self).__name__} is append-only; rows are never deleted.")


class SystemClock(models.Model):
    """Per-PC singleton for the clock-rollback guard (spec §6.7).

    Device state, not hotel data: it is not a BaseModel and is excluded from merge import.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    clock_blocked = models.BooleanField(default=False)
    blocked_at = models.DateTimeField(null=True, blank=True, help_text="Device time when the rollback was detected.")

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="system_clock_singleton")]

    def __str__(self):
        return f"SystemClock(last_seen_at={self.last_seen_at}, blocked={self.clock_blocked})"

    @classmethod
    def load(cls) -> "SystemClock":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class HotelSettings(BaseModel):
    """Hotel identity and operating rules (V2 artboard 6.11 D «بيانات الفندق»). One row per hotel."""

    class Digits(models.TextChoices):
        WESTERN = "western", "123"
        ARABIC = "arabic", "١٢٣"

    name_ar = models.CharField(max_length=120, default="فندق سكاي تاورز")
    name_latin = models.CharField(max_length=120, default="Sky Towers Hotel")
    address = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    currency = models.CharField(max_length=10, default="SDG", editable=False)
    digits = models.CharField(max_length=10, choices=Digits.choices, default=Digits.WESTERN)
    money_decimals = models.PositiveSmallIntegerField(default=0, help_text="0 or 2 decimals when showing money.")
    stay_day_end = models.TimeField(default="23:59", help_text="A stay becomes overdue after this time.")
    session_lock_minutes = models.PositiveSmallIntegerField(default=15)
    expense_attachment_threshold = MoneyField(default=2_000_000, help_text="Receipt required above (minor units).")
    max_discount_percent = models.PositiveSmallIntegerField(default=20)
    auto_print_receipt = models.BooleanField(default=True)
    thermal_printer = models.CharField(max_length=60, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["hotel_id"], name="one_settings_row_per_hotel")]

    def __str__(self):
        return self.name_ar

    @classmethod
    def load(cls) -> "HotelSettings":
        obj, _ = cls.objects.get_or_create(hotel_id=current_hotel_id())
        return obj
