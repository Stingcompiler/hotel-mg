"""Per-guest history numbers for the guest list and profile (artboard 6.8). Read-only."""

from apps.billing.services import balances_by_reservation
from apps.stays.models import Reservation, ReservationStatus

STAYED = (ReservationStatus.CHECKED_IN, ReservationStatus.CHECKED_OUT)


def _stays(guest_ids=None):
    qs = Reservation.objects.filter(status__in=STAYED).select_related("room")
    return qs if guest_ids is None else qs.filter(guest_id__in=guest_ids)


def for_guests(guest_ids) -> dict:
    """guest id → {stays_count, last_stay, debt, in_house}. Two aggregate queries plus one list query."""
    stays = list(_stays(guest_ids))
    balances = balances_by_reservation([r.pk for r in stays])
    out = {gid: {"stays_count": 0, "last_stay": None, "debt": 0, "in_house": False} for gid in guest_ids}
    for r in sorted(stays, key=lambda r: r.check_in_date):
        row = out[r.guest_id]
        row["stays_count"] += 1
        row["last_stay"] = {"reservation_id": r.pk, "check_in_date": r.check_in_date, "room": r.room.number}
        row["debt"] += max(balances[r.pk], 0)
        row["in_house"] = row["in_house"] or r.status == ReservationStatus.CHECKED_IN
    return out


def debtor_ids() -> set:
    stays = list(_stays().values_list("pk", "guest_id"))
    balances = balances_by_reservation([pk for pk, _ in stays])
    return {gid for pk, gid in stays if balances[pk] > 0}


def history(guest_id) -> list[dict]:
    """Every reservation of the guest, newest first, with money totals."""
    reservations = list(
        Reservation.objects.filter(guest_id=guest_id).select_related("room").order_by("-check_in_date", "-created_at")
    )
    balances = balances_by_reservation([r.pk for r in reservations])
    return [
        {
            "reservation_id": r.pk,
            "room": r.room.number if r.room_id else None,
            "check_in_date": r.check_in_date,
            "check_out_date": r.check_out_date,
            "nights": r.nights,
            "status": r.status,
            "status_label": r.get_status_display(),
            "balance": balances[r.pk],
        }
        for r in reservations
    ]
