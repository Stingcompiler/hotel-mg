"""Per-guest history numbers for the guest list and profile (artboard 6.8). Read-only."""

from django.db.models import Sum

from apps.billing.models import FolioLine, Payment
from apps.billing.services import balances_by_reservation
from apps.stays import rules as stay_rules
from apps.stays.models import Reservation, ReservationStatus

STAYED = (ReservationStatus.CHECKED_IN, ReservationStatus.CHECKED_OUT)
# A cancelled stay or a no-show can still owe (nights used, charges): it counts as a debt (review 2026-09-28, BIZ-6).
MAY_OWE = (*STAYED, ReservationStatus.CANCELLED, ReservationStatus.NO_SHOW)


def for_guests(guest_ids) -> dict:
    """guest id → {stays_count, last_stay, debt, in_house}. Two aggregate queries plus one list query."""
    owing = list(Reservation.objects.filter(status__in=MAY_OWE, guest_id__in=guest_ids).select_related("room"))
    balances = balances_by_reservation([r.pk for r in owing])
    out = {gid: {"stays_count": 0, "last_stay": None, "debt": 0, "in_house": False} for gid in guest_ids}
    for r in sorted(owing, key=lambda r: r.check_in_date):
        row = out[r.guest_id]
        row["debt"] += max(balances[r.pk], 0)
        if r.status not in STAYED:
            continue
        row["stays_count"] += 1
        row["last_stay"] = {"reservation_id": r.pk, "check_in_date": r.check_in_date, "room": r.room.number}
        row["in_house"] = row["in_house"] or r.status == ReservationStatus.CHECKED_IN
    return out


def debtor_ids() -> set:
    stays = list(Reservation.objects.filter(status__in=MAY_OWE).values_list("pk", "guest_id"))
    balances = balances_by_reservation([pk for pk, _ in stays])
    return {gid for pk, gid in stays if balances[pk] > 0}


def history(guest_id) -> list[dict]:
    """Every reservation of the guest, newest first, with money totals."""
    reservations = list(
        Reservation.objects.filter(guest_id=guest_id)
        .select_related("room", "stay")
        .order_by("-check_in_date", "-created_at")
    )
    ids = [r.pk for r in reservations]
    balances = balances_by_reservation(ids)
    charged = dict(
        FolioLine.objects.filter(folio__reservation_id__in=ids)
        .values_list("folio__reservation_id")
        .annotate(s=Sum("amount"))
    )
    paid = dict(
        Payment.objects.filter(folio__reservation_id__in=ids)
        .values_list("folio__reservation_id")
        .annotate(s=Sum("amount"))
    )
    return [
        {
            "reservation_id": r.pk,
            "room": r.room.number if r.room_id else None,
            "check_in_date": r.check_in_date,
            "check_out_date": r.check_out_date,
            "last_night": stay_rules.last_night(r.check_out_date),
            "nights": r.nights,
            "status": r.status,
            "status_label": r.get_status_display(),
            "duration_label": r.get_duration_kind_display(),
            "total": charged.get(r.pk) or 0,
            "paid": paid.get(r.pk) or 0,
            "balance": balances[r.pk],
            "stay": getattr(getattr(r, "stay", None), "pk", None),
        }
        for r in reservations
    ]
