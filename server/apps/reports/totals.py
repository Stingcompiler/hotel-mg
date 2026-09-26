"""Figures that must be identical on the reception PC and on the owner PC after importing its backups
(spec §9.3 property test, §12 B4 gate: «imports reproduce reception totals»)."""

from django.db.models import Count, Sum


def snapshot(using: str = "default") -> dict:
    from apps.accounts.models import User
    from apps.audit.models import AuditLog
    from apps.billing.models import FolioLine, Payment
    from apps.cash.models import Expense, Shift
    from apps.followups.models import FollowupTask
    from apps.guests.models import Guest
    from apps.rooms.models import Room
    from apps.stays.models import Reservation, Stay

    def total(model, field="amount"):
        return model.objects.using(using).aggregate(s=Sum(field))["s"] or 0

    return {
        "users": User.objects.using(using).count(),
        "rooms_by_status": dict(Room.objects.using(using).values_list("status").annotate(n=Count("pk"))),
        "guests": Guest.objects.using(using).count(),
        "reservations_by_status": dict(Reservation.objects.using(using).values_list("status").annotate(n=Count("pk"))),
        "reservations_total": total(Reservation, "total"),
        "stays": Stay.objects.using(using).count(),
        "charges": total(FolioLine),
        "payments": total(Payment),
        "expenses": total(Expense),
        "shifts": Shift.objects.using(using).count(),
        "tasks": FollowupTask.objects.using(using).count(),
        "audit_rows": AuditLog.objects.using(using).count(),
    }
