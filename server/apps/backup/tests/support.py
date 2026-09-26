"""Helpers shared by the backup tests."""

from pathlib import Path

from apps.backup import export, merge
from apps.billing import services as billing
from apps.guests.models import Guest
from apps.rooms.models import Room
from apps.stays import services as reservations
from apps.stays import stay_services


def walk_in(actor, room_number, name, nights=3, pay=0):
    guest = Guest.objects.create(full_name=name, search_name=name)
    room = Room.objects.get(number=room_number)
    stay = stay_services.book_and_check_in(
        actor,
        guest=guest,
        room_type=room.room_type,
        room=room,
        check_in_date=reservations.today(),
        duration_kind="daily",
        count=nights,
    )
    if pay:
        billing.record_payment(actor, billing.folio_of(stay.reservation).pk, amount=pay, method="cash")
    return stay


def backup(actor) -> Path:
    run = export.run_backup(actor)
    assert run.status == "ok", run.message
    return Path(run.path)


def do_import(path: Path, identity, **kw):
    return merge.import_backup(
        None, path.read_bytes(), source="file", file_name=path.name, target="owner", identity=identity, **kw
    )
