from django.db import models

from apps.core.models import AppendOnlyModel, BaseModel


class IdType(models.TextChoices):
    NATIONAL_ID = "national_id", "بطاقة وطنية"
    PASSPORT = "passport", "جواز سفر"
    DRIVING_LICENSE = "driving_license", "رخصة قيادة"
    OTHER = "other", "أخرى"


class Guest(BaseModel):
    full_name = models.CharField(max_length=120)
    search_name = models.CharField(max_length=120, db_index=True, editable=False)
    phone = models.CharField(max_length=20, blank=True, db_index=True, help_text="Normalized: + and digits.")
    nationality = models.CharField(max_length=40, blank=True)
    id_type = models.CharField(max_length=20, choices=IdType.choices, blank=True)
    id_number = models.CharField(max_length=40, blank=True, db_index=True, help_text="Manager/owner only.")
    warning_note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class Companion(BaseModel):
    guest = models.ForeignKey(Guest, on_delete=models.PROTECT, related_name="companions")
    name = models.CharField(max_length=120)
    relation = models.CharField(max_length=40, blank=True)
    # Replaced companions are flagged, not deleted: the owner PC's additive import never deletes.
    removed = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.name


class GuestDocument(AppendOnlyModel):
    """ID image stored under attachments/ after compression to ≤ 300 KB (spec §5)."""

    guest = models.ForeignKey(Guest, on_delete=models.PROTECT, related_name="documents")
    file_path = models.CharField(max_length=200, help_text="Relative to the attachments directory.")
    size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    content_type = models.CharField(max_length=40, default="image/jpeg")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.file_path
