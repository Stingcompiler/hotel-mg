"""`manage.py restore_full`: disaster recovery on the reception PC from an encrypted backup."""

import sqlite3
from io import StringIO

import pytest
from django.conf import settings
from django.core.management import CommandError, call_command

from apps.guests.models import Guest

from .support import backup, walk_in

pytestmark = pytest.mark.django_db(transaction=True, databases=["default", "owner", "incoming"])


def _restore(path, key, **kw):
    out = StringIO()
    call_command("restore_full", str(path), identity=str(key), yes=True, stdout=out, **kw)
    return out.getvalue()


def test_restore_replaces_database_and_attachments_and_keeps_the_old_files(hotel, owner_identity, tmp_path):
    stay = walk_in(hotel, "201", "محمد عثمان")
    doc = settings.RUNTIME.attachments_dir / "guests" / f"{stay.reservation.guest_id}.jpg"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_bytes(b"\xff\xd8 id photo")
    path = backup(hotel)
    key = tmp_path / "owner.key"  # the owner_identity fixture wrote it there

    # Something the running PC has now that the backup does not: it must end up in the pre-restore folder.
    settings.RUNTIME.db_path.write_bytes(b"not the backup")
    doc.write_bytes(b"changed later")

    out = _restore(path, key)
    assert "تم" in out
    con = sqlite3.connect(settings.RUNTIME.db_path)
    try:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        names = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    finally:
        con.close()
    assert "guests_guest" in names
    assert doc.read_bytes() == b"\xff\xd8 id photo"
    kept = list(settings.RUNTIME.backups_dir.glob("pre-restore-*"))
    assert len(kept) == 1 and (kept[0] / "hotel.db").read_bytes() == b"not the backup"
    assert (kept[0] / "attachments" / "guests" / doc.name).read_bytes() == b"changed later"
    assert Guest.objects.filter(full_name="محمد عثمان").exists()  # the live ORM database is untouched


def test_restore_refuses_wrong_key_foreign_hotel_and_owner_role(hotel, owner_identity, tmp_path, monkeypatch):
    from apps.backup import keys

    walk_in(hotel, "201", "محمد عثمان")
    path = backup(hotel)
    other = tmp_path / "other.key"
    keys.generate(other)
    with pytest.raises(CommandError, match="التوقيع"):
        _restore(path, other)
    with pytest.raises(CommandError, match="غير موجود"):
        _restore(tmp_path / "missing.age", tmp_path / "owner.key")
    import dataclasses

    monkeypatch.setattr(settings, "RUNTIME", dataclasses.replace(settings.RUNTIME, role="owner"))
    with pytest.raises(CommandError, match="reception"):
        _restore(path, tmp_path / "owner.key")
