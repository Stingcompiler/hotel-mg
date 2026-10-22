"""A backup number is never issued twice for a hotel, also after a restore (QA 2026-10-22, ج-1; decision 233)."""

import json
import sqlite3

import pytest
from django.conf import settings
from django.db import transaction

from apps.backup import adopt, export, keys, merge, rules
from apps.billing.models import Sequence
from apps.core.hotel import current_hotel_id
from service import pending_import

from .support import backup

pytestmark = pytest.mark.django_db(transaction=True, databases=["default", "owner", "incoming"])


def _counter() -> int:
    return Sequence.objects.get(hotel_id=current_hotel_id(), name="backup").last


def test_the_floor_is_the_highest_number_already_used_for_this_hotel():
    names = ["skytowers-5a7e0000-000004-20261022-1006.age", "skytowers-5a7e0000-000002-20261021-0900.age"]
    assert rules.backup_counter_floor(3, "5a7e0000", names) == 4  # a file ahead of the counter
    assert rules.backup_counter_floor(9, "5a7e0000", names) == 9  # the counter ahead of the files
    assert rules.backup_counter_floor(0, "5a7e0000", [], adopted_seq=12) == 12  # the file a PC was adopted from
    other = ["skytowers-11112222-000050-20261022-1006.age", "notes.txt", "skytowers-5a7e0000-x-20261022-1006.age"]
    assert rules.backup_counter_floor(1, "5a7e0000", other) == 1  # another hotel's files and stray names do not count


def test_a_backup_carries_its_own_number_so_a_restore_continues_after_it(hotel):
    path = backup(hotel)
    seq = rules.parse_file_name(path.name)[1]
    _manifest, files, _adopted = merge.open_backup(path.read_bytes(), keys.local_identities())
    copy = settings.RUNTIME.home / "restored.db"
    copy.write_bytes(files[rules.DB_FILE])
    with sqlite3.connect(copy) as db:
        (last,) = db.execute("select last from billing_sequence where name = 'backup'").fetchone()
    assert last == seq  # restored from backup N, the next backup is N + 1


def test_files_already_in_the_folder_are_never_numbered_again(hotel):
    first = backup(hotel)
    # A database restored from a file made before this fix: its counter is one behind the newest file.
    Sequence.objects.filter(hotel_id=current_hotel_id(), name="backup").update(last=0)
    second = backup(hotel)
    assert rules.parse_file_name(second.name)[1] == rules.parse_file_name(first.name)[1] + 1


def test_a_pc_adopted_to_work_continues_after_the_adopted_file(hotel):
    with transaction.atomic():
        export.raise_backup_counter()  # the counter row exists
    home = settings.RUNTIME.home
    pending = pending_import.pending_dir(home)
    pending.mkdir(parents=True, exist_ok=True)
    plan = {"mode": "work", "file_name": "b.age", "hotel_id": str(current_hotel_id()), "seq": 12, "applied": True}
    (pending / pending_import.PLAN).write_text(json.dumps(plan), encoding="utf-8")
    adopt.finish_pending()
    assert _counter() == 12
    assert not pending.exists()
    assert rules.parse_file_name(backup(hotel).name)[1] == 13
