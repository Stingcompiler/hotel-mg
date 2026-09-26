"""Room state machine (spec §6.3). Pure functions, no ORM.

ready ──check_in──▶ occupied ──checkout──▶ cleaning ──confirm_ready──▶ ready
ready ⇄ maintenance ; cleaning ⇄ maintenance     (never from occupied)
"""

from datetime import date

READY, OCCUPIED, CLEANING, MAINTENANCE = "ready", "occupied", "cleaning", "maintenance"

# (from, to) -> the only trigger allowed to make that move.
TRANSITIONS = {
    (READY, OCCUPIED): "check_in",
    (OCCUPIED, CLEANING): "checkout",
    (CLEANING, READY): "manual",
    (READY, MAINTENANCE): "manual",
    (MAINTENANCE, READY): "manual",
    (CLEANING, MAINTENANCE): "manual",
    (MAINTENANCE, CLEANING): "manual",
}


def can_transition(from_status: str, to_status: str, trigger: str) -> bool:
    """``trigger`` is "manual" (staff set-status), "check_in" or "checkout" (stay services)."""
    return TRANSITIONS.get((from_status, to_status)) == trigger


def manual_targets(from_status: str) -> list[str]:
    """Statuses staff may pick for a room currently in ``from_status``."""
    return sorted(to for (frm, to), trig in TRANSITIONS.items() if frm == from_status and trig == "manual")


def reason_required(to_status: str) -> bool:
    return to_status == MAINTENANCE


def is_overdue(status: str, today: date, check_out_date: date | None) -> bool:
    """Occupied past the end of the last night (check_out_date is exclusive)."""
    return status == OCCUPIED and check_out_date is not None and today >= check_out_date


def can_take_out_of_service(status: str) -> bool:
    """An occupied room cannot be taken out of service (Settings → Rooms note)."""
    return status != OCCUPIED


def is_bookable(status: str, in_service: bool) -> bool:
    """Can be assigned to a stay starting now."""
    return in_service and status == READY
