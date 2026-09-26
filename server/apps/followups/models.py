from django.db import models

from apps.core.fields import MoneyField
from apps.core.models import AppendOnlyModel, BaseModel


class TriggerKind(models.TextChoices):
    STAY_ENDING = "stay_ending", "انتهاء الإقامة"
    STAY_OVERDUE = "stay_overdue", "إقامة متجاوزة"
    CHECKOUT_DEBT = "checkout_debt", "خروج بدين"
    SHIFT_OPEN_TOO_LONG = "shift_open_too_long", "وردية مفتوحة طويلًا"
    ROOM_CLEANING_TOO_LONG = "room_cleaning_too_long", "تنظيف متأخر"
    ROOM_MAINTENANCE_TOO_LONG = "room_maintenance_too_long", "صيانة طويلة"
    NO_BACKUP = "no_backup", "لا نسخة احتياطية"
    NO_DRIVE_UPLOAD = "no_drive_upload", "لا رفع إلى Drive"


class AlertRule(BaseModel):
    """Manager-editable alert rule (spec §6.6, artboard 6.11 «قواعد التنبيه»).

    For stay_ending: first alert ``days_before`` the last night at ``at_time``, optional second alert,
    then every ``repeat_hours`` until someone acts. Other triggers use ``threshold_hours`` or ``threshold``.
    """

    name = models.CharField(max_length=80)
    trigger_kind = models.CharField(max_length=30, choices=TriggerKind.choices)
    duration_kind = models.CharField(max_length=10, blank=True, help_text="stay_ending: daily / weekly / monthly.")
    days_before = models.PositiveSmallIntegerField(default=0)
    second_days_before = models.PositiveSmallIntegerField(null=True, blank=True)
    at_time = models.TimeField(default="09:00")
    repeat_hours = models.PositiveSmallIntegerField(default=12, help_text="0 = no repeat.")
    max_snoozes = models.PositiveSmallIntegerField(default=3)
    escalate_after_hours = models.PositiveSmallIntegerField(default=24, help_text="Open this long → neglected.")
    threshold_hours = models.PositiveIntegerField(null=True, blank=True, help_text="shift/room/backup triggers.")
    threshold = MoneyField(null=True, blank=True, help_text="checkout_debt: balance above this (minor units).")
    windows_notification = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["trigger_kind", "duration_kind"]

    def __str__(self):
        return self.name


class FollowupTask(BaseModel):
    """One thing someone must act on. Closed only by an action (spec §6.6); never deleted."""

    class Status(models.TextChoices):
        OPEN = "open", "مفتوحة"
        SNOOZED = "snoozed", "مؤجلة"
        WAITING = "waiting", "بانتظار الرد"
        DONE = "done", "منجزة"
        SUPERSEDED = "superseded", "مستبدلة"
        NEGLECTED = "neglected", "مُهمَلة"

    rule = models.ForeignKey(AlertRule, on_delete=models.PROTECT, related_name="tasks")
    subject_key = models.CharField(max_length=80, help_text="stay:<id> / room:<id> / shift:<id>")
    stay = models.ForeignKey("stays.Stay", null=True, blank=True, on_delete=models.PROTECT, related_name="tasks")
    room = models.ForeignKey("rooms.Room", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    shift = models.ForeignKey(
        "cash.Shift",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Subject shift, or the shift that was open when the task became neglected.",
    )
    title = models.CharField(max_length=120)
    due_at = models.DateTimeField()
    due_date = models.DateField()
    second_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    snooze_count = models.PositiveSmallIntegerField(default=0)
    next_at = models.DateTimeField(null=True, blank=True, help_text="When a snoozed/waiting task comes back.")
    note = models.CharField(max_length=300, blank=True, help_text="Latest «بانتظار الرد» note.")
    last_notified_at = models.DateTimeField(null=True, blank=True)
    neglected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_at"]
        constraints = [
            # Idempotent engine: re-runs never duplicate (spec §6.6).
            models.UniqueConstraint(fields=["rule", "subject_key", "due_date"], name="task_once_per_rule_subject_day"),
        ]
        indexes = [models.Index(fields=["status", "due_at"])]

    def __str__(self):
        return f"{self.title} ({self.status})"


class TaskAction(AppendOnlyModel):
    """What someone did about a task, with who and when: the owner's accountability trail."""

    class Action(models.TextChoices):
        EXTEND = "extend", "تمديد"
        CONFIRM_CHECKOUT = "confirm_checkout", "تأكيد المغادرة"
        WAITING = "waiting", "بانتظار الرد"
        SNOOZE = "snooze", "تأجيل"
        DONE = "done", "تم"

    task = models.ForeignKey(FollowupTask, on_delete=models.PROTECT, related_name="actions")
    action = models.CharField(max_length=20, choices=Action.choices)
    at = models.DateTimeField()
    note = models.CharField(max_length=300, blank=True)
    next_at = models.DateTimeField(null=True, blank=True)
    shift = models.ForeignKey("cash.Shift", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["at"]

    def __str__(self):
        return f"{self.task}: {self.action}"


class Toast(AppendOnlyModel):
    """A Windows notification to show; the tray polls for new ones (spec §6.6, artboard 6.6 B)."""

    task = models.ForeignKey(FollowupTask, on_delete=models.PROTECT, related_name="toasts")
    seq = models.PositiveBigIntegerField(db_index=True, help_text="Poll cursor.")
    title = models.CharField(max_length=60)
    body = models.CharField(max_length=120)
    at = models.DateTimeField()

    class Meta:
        ordering = ["seq"]

    def __str__(self):
        return self.title
