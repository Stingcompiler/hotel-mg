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


class Currency(BaseModel):
    """A foreign currency the hotel accepts, with the owner's rate (owner decision 2026-09-28).

    ``rate`` is the base currency in minor units for one whole unit (1 USD = 2,500 ج.س → 250000). A payment keeps
    its own copy of the rate, so changing it later never touches past receipts. Never deleted: ``is_active``.
    """

    code = models.CharField(max_length=3, help_text="ISO 4217, e.g. USD.")
    name = models.CharField(max_length=40)
    symbol = models.CharField(max_length=6, blank=True)
    rate = MoneyField(help_text="Base-currency minor units for one whole unit of this currency.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["hotel_id", "code"], name="currency_code_per_hotel"),
            models.CheckConstraint(condition=models.Q(rate__gt=0), name="currency_rate_positive"),
        ]

    def __str__(self):
        return self.code

    @property
    def label(self) -> str:
        return self.symbol or self.code


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
        indexes = [models.Index(fields=["posted_at"]), models.Index(fields=["folio", "amount"])]
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
    # Paid in a foreign currency: what the guest handed over and the rate used; ``amount`` is its base equivalent.
    currency = models.CharField(max_length=3, blank=True, help_text="Empty: the base currency; else ISO code (USD).")
    foreign_amount = models.BigIntegerField(null=True, blank=True, help_text="Signed minor units (cents) of currency.")
    rate = models.BigIntegerField(null=True, blank=True, help_text="Base minor units per whole unit, at the time.")

    class Meta:
        ordering = ["received_at", "created_at"]
        indexes = [models.Index(fields=["received_at"]), models.Index(fields=["folio", "amount"])]
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
        """«دفعة — غرفة 204 · فاطمة أحمد النور» as in the shift movements; «(150 $)» when paid in a foreign currency."""
        reservation = self.folio.reservation
        room = f"غرفة {reservation.room.number}" if reservation.room_id else "بلا غرفة"
        text = f"{self.get_kind_display()} — {room} · {reservation.guest.full_name}"
        if self.currency:
            text = f"{text} ({self.foreign_text()})"
        return f"{text} — {self.reason}" if self.reason else text

    def foreign_text(self) -> str:
        """«150 $ بسعر 2,500» — empty for a base-currency payment."""
        from . import rules

        if not self.currency:
            return ""
        symbol = Currency.objects.filter(code=self.currency).values_list("symbol", flat=True).first() or self.currency
        return f"{rules.foreign_text(self.foreign_amount, symbol)} بسعر {rules.rate_text(self.rate)}"
