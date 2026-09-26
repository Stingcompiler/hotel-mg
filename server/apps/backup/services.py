from django.db import transaction

from apps.audit import services as audit
from apps.core.concurrency import get_for_update

from . import export
from .models import BackupSettings


@transaction.atomic
def update_settings(actor, *, version: int, **changes) -> BackupSettings:
    row = get_for_update(BackupSettings.objects, export.backup_settings().pk, version)
    before = audit.snapshot(row)
    for field, value in changes.items():
        setattr(row, field, value)
    row.save()
    audit.record(
        actor=actor,
        action="backup.settings",
        entity="backup_settings",
        entity_id=row.pk,
        before=before,
        after=audit.snapshot(row),
    )
    return row


def after_shift_close() -> None:
    """«نسخة عند إغلاق كل وردية»: runs once the closing transaction has committed (VACUUM needs no transaction)."""
    if export.backup_settings().on_shift_close:
        transaction.on_commit(lambda: export.run_backup(kind="shift_close"))
