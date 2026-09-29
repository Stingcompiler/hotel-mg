from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from apps.core.fields import MoneyField
from apps.core.models import BaseModel


class DurationKind(models.TextChoices):
    DAILY = "daily", "يومي"
    WEEKLY = "weekly", "أسبوعي"
    MONTHLY = "monthly", "شهري"
    MIXED = "mixed", "مختلط"


class ReservationStatus(models.TextChoices):
    CONFIRMED = "confirmed", "مؤكد"
    CHECKED_IN = "checked_in", "مسكّن"
    CHECKED_OUT = "checked_out", "غادر"
    CANCELLED = "cancelled", "ملغى"
    NO_SHOW = "no_show", "لم يحضر"


class Reservation(BaseModel):
    """A booked period. Dates are hotel-local; ``check_out_date`` is exclusive (spec §5)."""

    guest = models.ForeignKey("guests.Guest", on_delete=models.PROTECT, related_name="reservations")
    room_type = models.ForeignKey("rooms.RoomType", on_delete=models.PROTECT, related_name="+")
    room = models.ForeignKey("rooms.Room", null=True, blank=True, on_delete=models.PROTECT, related_name="reservations")
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    duration_kind = models.CharField(max_length=10, choices=DurationKind.choices)
    duration_count = models.PositiveSmallIntegerField(help_text="Units of duration_kind; nights when mixed.")
    status = models.CharField(max_length=12, choices=ReservationStatus.choices, default=ReservationStatus.CONFIRMED)
    # Prices, chosen decomposition and any override at booking time. Later price edits never touch it.
    rate_snapshot = models.JSONField(encoder=DjangoJSONEncoder)
    total = MoneyField(help_text="Agreed room charge in minor units (override if any, else base).")
    notes = models.CharField(max_length=300, blank=True)
    status_reason = models.CharField(max_length=300, blank=True, help_text="Why it was cancelled / no-show.")

    class Meta:
        ordering = ["check_in_date", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(check_out_date__gt=models.F("check_in_date")),
                name="reservation_dates_ordered",
            ),
            models.CheckConstraint(condition=models.Q(total__gte=0), name="reservation_total_not_negative"),
        ]
        indexes = [
            models.Index(fields=["room", "status", "check_in_date"]),
            models.Index(fields=["status", "check_out_date"]),
            models.Index(fields=["check_in_date"]),
        ]

    def __str__(self):
        return f"{self.guest} {self.check_in_date}→{self.check_out_date}"

    @property
    def nights(self) -> int:
        return (self.check_out_date - self.check_in_date).days


class Stay(BaseModel):
    """Created at check-in (spec §5). Its state follows the reservation's status."""

    reservation = models.OneToOneField(Reservation, on_delete=models.PROTECT, related_name="stay")
    checked_in_at = models.DateTimeField()
    checked_out_at = models.DateTimeField(null=True, blank=True)
    # Filled when checkout or cancellation was forced through by a manager (e.g. leaving with a balance).
    override_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    override_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-checked_in_at"]
        indexes = [models.Index(fields=["checked_in_at"]), models.Index(fields=["checked_out_at"])]

    def __str__(self):
        return f"Stay {self.reservation}"


class StaySegment(BaseModel):
    """The room occupied over a date range. A room change closes one segment and opens the next."""

    stay = models.ForeignKey(Stay, on_delete=models.PROTECT, related_name="segments")
    room = models.ForeignKey("rooms.Room", on_delete=models.PROTECT, related_name="+")
    from_date = models.DateField()
    to_date = models.DateField(help_text="Exclusive.")
    reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["from_date", "created_at"]
        indexes = [models.Index(fields=["to_date"])]
        constraints = [
            models.CheckConstraint(condition=models.Q(to_date__gte=models.F("from_date")), name="segment_dates_ordered")
        ]

    def __str__(self):
        return f"{self.room} {self.from_date}→{self.to_date}"
