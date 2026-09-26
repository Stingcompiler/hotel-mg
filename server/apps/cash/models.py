from django.db import models

from apps.core.fields import MoneyField
from apps.core.models import AppendOnlyModel, BaseModel


class PaymentMethod(models.TextChoices):
    CASH = "cash", "نقدي"
    BANKAK = "bankak", "بنكك"
    TRANSFER = "transfer", "تحويل"


class ExpenseCategory(models.TextChoices):
    SUPPLIES = "supplies", "مستلزمات"
    PURCHASES = "purchases", "مشتريات"
    MAINTENANCE = "maintenance", "صيانة"
    BILLS = "bills", "فواتير"
    SALARIES = "salaries", "رواتب"
    OTHER = "other", "أخرى"


class Shift(BaseModel):
    """A cash-drawer session (spec §5, §6.5). Exactly one open shift per device.

    ``created_by`` opened it; ``closed_by`` may be the next person at the desk.
    Expected cash = opening + Σ cash payments − Σ cash expenses (stored at close).
    """

    device = models.CharField(max_length=64)
    opened_at = models.DateTimeField()
    opening = MoneyField()
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    expected = MoneyField(null=True, blank=True)
    counted = MoneyField(null=True, blank=True)
    difference_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel_id", "device"],
                condition=models.Q(closed_at__isnull=True),
                name="one_open_shift_per_device",
            ),
            models.CheckConstraint(condition=models.Q(opening__gte=0), name="shift_opening_not_negative"),
        ]

    def __str__(self):
        return f"{self.device} {self.opened_at:%Y-%m-%d %H:%M}"

    @property
    def difference(self) -> int | None:
        return None if self.counted is None or self.expected is None else self.counted - self.expected


class Expense(AppendOnlyModel):
    """Money out. Never edited or deleted: a mistake is corrected by a reversing row (spec §5)."""

    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name="expenses")
    category = models.CharField(max_length=20, choices=ExpenseCategory.choices)
    amount = MoneyField(help_text="Positive for an expense; negative for a reversal.")
    note = models.CharField(max_length=300)
    method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    reference = models.CharField(max_length=60, blank=True)
    room = models.ForeignKey("rooms.Room", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    spent_at = models.DateTimeField()
    reverses = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversed_by")
    reason = models.CharField(max_length=300, blank=True, help_text="Required on reversals.")
    number = models.PositiveIntegerField(null=True, help_text="Gap-free per hotel; printed as EXP-000123.")

    class Meta:
        ordering = ["-spent_at"]
        constraints = [
            models.CheckConstraint(condition=~models.Q(amount=0), name="expense_amount_not_zero"),
            models.UniqueConstraint(fields=["hotel_id", "number"], name="expense_number_per_hotel"),
        ]

    def __str__(self):
        return f"{self.get_category_display()} {self.amount}"

    @property
    def label(self) -> str:
        return f"EXP-{self.number:06d}" if self.number else ""


class ExpenseAttachment(AppendOnlyModel):
    """Receipt photo, compressed like ID images. Can be added after the expense (design: «بانتظار مرفق»)."""

    expense = models.ForeignKey(Expense, on_delete=models.PROTECT, related_name="attachments")
    file_path = models.CharField(max_length=200)
    size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)

    def __str__(self):
        return self.file_path
