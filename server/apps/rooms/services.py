from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.core.concurrency import get_for_update
from apps.core.errors import ApiError

from . import rules
from .models import Room, RoomStatus, RoomStatusHistory, RoomType

PRICE_FIELDS = frozenset({"nightly_price", "weekly_price", "monthly_price"})
ROOM_FIELDS = ["number", "floor", "room_type", "status", "maintenance_reason", "in_service", "note"]


def _label(status: str) -> str:
    return RoomStatus(status).label


# --- Room types -----------------------------------------------------------------


@transaction.atomic
def create_room_type(actor, **fields) -> RoomType:
    room_type = RoomType.objects.create(created_by=actor, **fields)
    audit.record(
        actor=actor,
        action="room_type.create",
        entity="room_type",
        entity_id=room_type.pk,
        after=audit.snapshot(room_type),
    )
    return room_type


@transaction.atomic
def update_room_type(actor, room_type_id, *, version: int, **changes) -> RoomType:
    """Price edits apply to new reservations only; existing ones keep their rate snapshot."""
    room_type = get_for_update(RoomType.objects, room_type_id, version)
    before = audit.snapshot(room_type)
    for field, value in changes.items():
        setattr(room_type, field, value)
    room_type.save()
    action = "room_type.update_prices" if PRICE_FIELDS & changes.keys() else "room_type.update"
    audit.record(
        actor=actor,
        action=action,
        entity="room_type",
        entity_id=room_type.pk,
        before=before,
        after=audit.snapshot(room_type),
    )
    return room_type


# --- Rooms ----------------------------------------------------------------------


@transaction.atomic
def create_room(actor, *, number, floor, room_type, note="") -> Room:
    room = Room.objects.create(
        number=number,
        floor=floor,
        room_type=room_type,
        note=note,
        status_changed_at=timezone.now(),
        created_by=actor,
    )
    audit.record(
        actor=actor, action="room.create", entity="room", entity_id=room.pk, after=audit.snapshot(room, ROOM_FIELDS)
    )
    return room


@transaction.atomic
def update_room(actor, room_id, *, version: int, **changes) -> Room:
    """Edit number/floor/type/note/in-service. Changing the type does not touch current stays."""
    room = get_for_update(Room.objects, room_id, version)
    if changes.get("in_service") is False and not rules.can_take_out_of_service(room.status):
        raise ApiError("room_occupied", 409)
    before = audit.snapshot(room, ROOM_FIELDS)
    for field, value in changes.items():
        setattr(room, field, value)
    room.save()
    audit.record(
        actor=actor,
        action="room.update",
        entity="room",
        entity_id=room.pk,
        before=before,
        after=audit.snapshot(room, ROOM_FIELDS),
    )
    return room


def transition(room: Room, to_status: str, *, trigger: str, actor, reason: str = "") -> Room:
    """Move a locked room along the state machine; writes history. Caller owns the transaction and audit."""
    if not rules.can_transition(room.status, to_status, trigger):
        raise ApiError(
            "invalid_room_transition",
            409,
            detail=f"لا يمكن نقل الغرفة {room.number} من «{_label(room.status)}» إلى «{_label(to_status)}».",
            allowed=rules.manual_targets(room.status),
        )
    reason = reason.strip()
    if rules.reason_required(to_status) and not reason:
        raise ApiError("reason_required", 400)
    now = timezone.now()
    RoomStatusHistory.objects.create(
        room=room, from_status=room.status, to_status=to_status, at=now, reason=reason, created_by=actor
    )
    room.status = to_status
    room.status_changed_at = now
    room.maintenance_reason = reason if to_status == RoomStatus.MAINTENANCE else ""
    room.save(update_fields=["status", "status_changed_at", "maintenance_reason"])
    return room


@transaction.atomic
def set_status(actor, room_id, to_status: str, *, reason: str = "", version: int | None = None) -> Room:
    """Staff action from the room board: confirm cleaned, start/end maintenance."""
    room = get_for_update(Room.objects, room_id, version)
    before = audit.snapshot(room, ["status", "maintenance_reason"])
    transition(room, to_status, trigger="manual", actor=actor, reason=reason)
    audit.record(
        actor=actor,
        action="room.set_status",
        entity="room",
        entity_id=room.pk,
        before=before,
        after=audit.snapshot(room, ["status", "maintenance_reason"]),
    )
    return room
