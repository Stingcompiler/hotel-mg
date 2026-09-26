from django.db import models

from apps.cash.models import PaymentMethod
from apps.core.fields import MoneyField
from apps.core.models import AppendOnlyModel, BaseModel


class Sequence(models.Model):
    """Gap-free per-hotel counters (invoice and receipt numbers).

    Incremented inside the transaction that uses the number, so a rollback returns it (spec §5).
    Numbers are issued on the reception PC only; the table is not merged into the owner PC.
    """

    hotel_id = models.UUIDField()
    name = models.CharField(max_length=20)
    last = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["hotel_id", "name"], name="sequence_per_hotel")]

    def __str__(self):
        return f"{self.name}={self.last}"


class Folio(BaseModel):
    """The bill of one reservation. Created at booking so deposits can be taken before arrival.

    Balance = Σ lines − Σ payments; computed, never stored (spec §6.4).
    """

    class Status(models.TextChoices):
        OPEN = "open", "مفتوحة"
        CLOSED = "closed", "مغلقة"

    reservation = models.OneToOneField("stays.Reservation", on_delete=models.PROTECT, related_name="folio")
    invoice_no = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)

    class Meta:
        ordering = ["-invoice_no"]
        constraints = [models.UniqueConstraint(fields=["hotel_id", "invoice_no"], name="invoice_no_per_hotel")]

    def __str__(self):
        return self.invoice_label

    @property
    def invoice_label(self) -> str:
        return f"INV-{self.invoice_no:06d}"


class FolioLine(AppendOnlyModel):
    """A charge (+) or credit (−). Never edited: a mistake gets a reversing line pointing to it."""

    class Kind(models.TextChoices):
        ROOM = "room", "إقامة"
        SERVICE = "service", "خدمة"
        DISCOUNT = "discount", "خصم"
        ADJUSTMENT = "adjustment", "تسوية"
        TAX = "tax", "ضريبة"
        REVERSAL = "reversal", "عكس"

    folio = models.ForeignKey(Folio, on_delete=models.PROTECT, related_name="lines")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    description = models.CharField(max_length=200)
    amount = MoneyField(help_text="Signed minor units: charges +, discounts/credits −.")
    reverses = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversed_by")
    reason = models.CharField(max_length=300, blank=True)
    posted_at = models.DateTimeField()

    class Meta:
        ordering = ["posted_at", "created_at"]
        constraints = [models.CheckConstraint(condition=~models.Q(amount=0), name="folio_line_not_zero")]

    def __str__(self):
        return f"{self.description} {self.amount}"


class Payment(AppendOnlyModel):
    """Money received (+) or paid back (−) on a folio, always inside an open shift (spec §6.5)."""

    class Kind(models.TextChoices):
        DEPOSIT = "deposit", "عربون"
        PAYMENT = "payment", "دفعة"
        REFUND = "refund", "ردّ"
        REVERSAL = "reversal", "عكس دفعة"

    folio = models.ForeignKey(Folio, on_delete=models.PROTECT, related_name="payments")
    shift = models.ForeignKey("cash.Shift", on_delete=models.PROTECT, related_name="payments")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    amount = MoneyField(help_text="Signed minor units: received +, refunded/reversed −.")
    reference = models.CharField(max_length=60, blank=True, help_text="Bankak / transfer reference.")
    verified = models.BooleanField(default=False, help_text="Non-cash reference checked against the bank app.")
    receipt_no = models.PositiveIntegerField()
    reverses = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversed_by")
    reason = models.CharField(max_length=300, blank=True)
    received_at = models.DateTimeField()

    class Meta:
        ordering = ["received_at", "created_at"]
        constraints = [
            models.CheckConstraint(condition=~models.Q(amount=0), name="payment_not_zero"),
            models.UniqueConstraint(fields=["hotel_id", "receipt_no"], name="receipt_no_per_hotel"),
        ]

    def __str__(self):
        return f"{self.receipt_label} {self.amount}"

    @property
    def receipt_label(self) -> str:
        return f"RCP-{self.receipt_no:06d}"

    def description(self) -> str:
        """«دفعة — غرفة 204 · فاطمة أحمد النور» as in the shift movements."""
        reservation = self.folio.reservation
        room = f"غرفة {reservation.room.number}" if reservation.room_id else "بلا غرفة"
        text = f"{self.get_kind_display()} — {room} · {reservation.guest.full_name}"
        return f"{text} — {self.reason}" if self.reason else text
