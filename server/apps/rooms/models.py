from django.db import models

from apps.core.fields import MoneyField
from apps.core.models import AppendOnlyModel, BaseModel


class RoomStatus(models.TextChoices):
    """Operational state (spec §6.3). "Overdue" is derived from the stay, never stored."""

    READY = "ready", "جاهزة"
    OCCUPIED = "occupied", "مشغولة"
    CLEANING = "cleaning", "تحتاج تنظيف"
    MAINTENANCE = "maintenance", "صيانة"


class RoomType(BaseModel):
    """Prices are snapshotted into reservations; editing them never touches existing stays (spec §5)."""

    name = models.CharField(max_length=40)
    capacity = models.PositiveSmallIntegerField(default=1)
    nightly_price = MoneyField()
    weekly_price = MoneyField(help_text="7 nights")
    monthly_price = MoneyField(help_text="30 nights")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["nightly_price", "name"]
        constraints = [
            models.UniqueConstraint(fields=["hotel_id", "name"], name="room_type_name_per_hotel"),
            models.CheckConstraint(
                condition=models.Q(nightly_price__gte=0, weekly_price__gte=0, monthly_price__gte=0),
                name="room_type_prices_not_negative",
            ),
        ]

    def __str__(self):
        return self.name


class Room(BaseModel):
    number = models.CharField(max_length=10)
    # Optional name next to the number («الشقة العائلية», «الجناح الملكي») — owner request 2026-09-28.
    name = models.CharField(max_length=60, blank=True)
    floor = models.SmallIntegerField()
    room_type = models.ForeignKey(RoomType, on_delete=models.PROTECT, related_name="rooms")
    status = models.CharField(max_length=16, choices=RoomStatus.choices, default=RoomStatus.READY)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    maintenance_reason = models.CharField(max_length=200, blank=True)
    # Out of service (Settings → Rooms): cannot be booked, excluded from occupancy.
    in_service = models.BooleanField(default=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [models.UniqueConstraint(fields=["hotel_id", "number"], name="room_number_per_hotel")]

    def __str__(self):
        return self.number


class RoomStatusHistory(AppendOnlyModel):
    """Every status change; source of the vacancy-period report (spec §5)."""

    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="status_history")
    from_status = models.CharField(max_length=16, choices=RoomStatus.choices)
    to_status = models.CharField(max_length=16, choices=RoomStatus.choices)
    at = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-at"]
        indexes = [models.Index(fields=["room", "at"])]

    def __str__(self):
        return f"{self.room}: {self.from_status} → {self.to_status}"
