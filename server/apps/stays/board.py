"""Room board data (spec §10.4: GET rooms?view=board): every room with its state, current stay and next booking."""

from apps.billing.services import balances_by_reservation
from apps.rooms import rules as room_rules
from apps.rooms.models import Room

from . import rules
from .models import Reservation, ReservationStatus
from .services import today


def board() -> dict:
    day = today()
    rooms = list(Room.objects.select_related("room_type").order_by("number"))
    current = {
        r.room_id: r
        for r in Reservation.objects.filter(status=ReservationStatus.CHECKED_IN).select_related(
            "guest", "stay", "folio"
        )
    }
    balances = balances_by_reservation([r.pk for r in current.values()])
    upcoming: dict = {}
    for r in (
        Reservation.objects.filter(status=ReservationStatus.CONFIRMED, check_in_date__gte=day)
        .exclude(room=None)
        .select_related("guest")
        .order_by("check_in_date")
    ):
        upcoming.setdefault(r.room_id, r)

    rows = []
    for room in rooms:
        stay = current.get(room.pk)
        overdue = room_rules.is_overdue(room.status, day, stay.check_out_date if stay else None)
        row = {
            "id": room.pk,
            "number": room.number,
            "floor": room.floor,
            "room_type": room.room_type_id,
            "room_type_name": room.room_type.name,
            "status": room.status,
            "display_status": "overdue" if overdue else room.status,
            "status_changed_at": room.status_changed_at,
            "maintenance_reason": room.maintenance_reason,
            "in_service": room.in_service,
            "manual_targets": room_rules.manual_targets(room.status),
            "version": room.version,
            "stay": None,
            "next_reservation": None,
        }
        if stay:
            last = rules.last_night(stay.check_out_date)
            row["stay"] = {
                "id": stay.stay.pk,
                "reservation": stay.pk,
                "guest_name": stay.guest.full_name,
                "guest_phone": stay.guest.phone,
                "check_in_date": stay.check_in_date,
                "check_out_date": stay.check_out_date,
                "last_night": last,
                "days_left": (last - day).days,  # 0 = ends today, negative = overdue by N days
                "duration_kind": stay.duration_kind,
                "duration_label": stay.get_duration_kind_display(),
                "balance": balances.get(stay.pk),
                "invoice": stay.folio.invoice_label if hasattr(stay, "folio") else None,
            }
        if nxt := upcoming.get(room.pk):
            row["next_reservation"] = {
                "id": nxt.pk,
                "guest_name": nxt.guest.full_name,
                "check_in_date": nxt.check_in_date,
                "duration_kind": nxt.duration_kind,
                "duration_label": nxt.get_duration_kind_display(),
            }
        rows.append(row)

    in_service = [r for r in rows if r["in_service"]]
    occupied = sum(1 for r in in_service if r["status"] == "occupied")
    summary = {
        "rooms": len(in_service),
        "occupied": occupied,
        "occupancy_percent": round(100 * occupied / len(in_service)) if in_service else 0,
        "arrivals_today": Reservation.objects.filter(status=ReservationStatus.CONFIRMED, check_in_date=day).count(),
        "departures_today": sum(1 for r in rows if r["stay"] and r["stay"]["days_left"] == 0),
        "overdue": sum(1 for r in rows if r["display_status"] == "overdue"),
        "by_status": {
            s: sum(1 for r in rows if r["status"] == s) for s in ("ready", "occupied", "cleaning", "maintenance")
        },
    }
    return {"date": day, "summary": summary, "rooms": rows}
