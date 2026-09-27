from django.db import models

from apps.core.models import AppendOnlyModel, BaseModel


class BackupSettings(BaseModel):
    """Settings → النسخ الاحتياطي (artboard 6.13 A). One row per hotel."""

    owner_recipient = models.CharField(
        max_length=200, blank=True, help_text="Owner's age public key (age1…); backups are encrypted to it."
    )
    interval_hours = models.PositiveSmallIntegerField(default=6)
    keep_count = models.PositiveSmallIntegerField(default=30)
    keep_days = models.PositiveSmallIntegerField(
        default=90, help_text="Backups older than this are deleted; 0 = never."
    )
    on_shift_close = models.BooleanField(default=True)
    auto_drive = models.BooleanField(default=True)
    second_dir = models.CharField(max_length=260, blank=True, help_text="USB / external disk folder.")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["hotel_id"], name="one_backup_settings_per_hotel")]

    def __str__(self):
        return f"every {self.interval_hours} h, keep {self.keep_count}"


class BackupRun(AppendOnlyModel):
    """One attempt to write an encrypted backup (spec §9.1). Device state: not merged into the owner PC."""

    class Kind(models.TextChoices):
        MANUAL = "manual", "يدوي"
        SCHEDULED = "scheduled", "مجدول"
        SHIFT_CLOSE = "shift_close", "عند الإغلاق"

    class Status(models.TextChoices):
        OK = "ok", "تمت"
        FAILED = "failed", "فشلت"
        SKIPPED = "skipped", "تخطّي"

    kind = models.CharField(max_length=12, choices=Kind.choices)
    status = models.CharField(max_length=10, choices=Status.choices)
    seq = models.PositiveIntegerField(null=True, blank=True, help_text="Per-hotel backup number (ok runs only).")
    full = models.BooleanField(default=False, help_text="All attachments (weekly), else changed ones only.")
    path = models.CharField(max_length=300, blank=True)
    second_path = models.CharField(max_length=300, blank=True)
    second_error = models.CharField(max_length=300, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    audit_seq = models.PositiveBigIntegerField(default=0, help_text="Last audit seq included; detects «no changes».")
    message = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.seq} {self.kind} {self.status}"


class DriveUpload(AppendOnlyModel):
    """Upload attempt of a backup file to Google Drive (spec §9.2)."""

    run = models.ForeignKey(BackupRun, on_delete=models.PROTECT, related_name="uploads")
    ok = models.BooleanField()
    drive_file_id = models.CharField(max_length=120, blank=True)
    message = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at"]


class ImportRun(AppendOnlyModel):
    """Owner PC: one import attempt (spec §9.3). ``counts`` = table → {inserted, updated, ignored}."""

    class Source(models.TextChoices):
        DRIVE = "drive", "Drive"
        FILE = "file", "USB"

    class Status(models.TextChoices):
        OK = "ok", "اكتمل"
        FAILED = "failed", "مرفوض"

    source = models.CharField(max_length=10, choices=Source.choices)
    file_name = models.CharField(max_length=200)
    backup_seq = models.PositiveIntegerField(null=True, blank=True)
    data_as_of = models.DateTimeField(null=True, blank=True, help_text="created_at in the imported manifest.")
    status = models.CharField(max_length=10, choices=Status.choices)
    counts = models.JSONField(default=dict)
    checks = models.JSONField(default=list, help_text="[{key, label, detail, status}] — the five pre-merge checks.")
    audit_chain_ok = models.BooleanField(null=True)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at"]


class BackupKeySlot(BaseModel):
    """1.1: the hotel key wrapped with one owner's or manager's password (keyslots.py). Device state: it travels
    inside each backup's header, never through the owner PC's merge."""

    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="backup_key_slot")
    wrapped = models.TextField(help_text="age passphrase-encrypted hotel identity, base64.")
    recipient = models.CharField(max_length=100, help_text="The hotel public key this slot opens.")

    def __str__(self):
        return f"slot {self.user}"
