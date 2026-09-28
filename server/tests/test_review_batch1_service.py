"""Review 2026-09-28, batch 1: start-up safety (BAK-5, BAK-7, WIN-1 logging)."""

import json
import logging

import pytest

from config import runtime
from service import pending_import, run_waitress


def _home(tmp_path, mode="work"):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "hotel.db").write_bytes(b"empty install")
    (tmp_path / "config.json").write_text(json.dumps({"role": "reception", "hotel_id": "new-pc"}), encoding="utf-8")
    pending = pending_import.pending_dir(tmp_path)
    pending.mkdir()
    (pending / "hotel.db").write_bytes(b"the hotel")
    plan = {"mode": mode, "hotel_id": "5a7e0000-0000-4000-8000-000000000001", "file_name": "b.age", "seq": 3}
    (pending / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    return pending


@pytest.mark.parametrize("cut_after", ["kept", "moved_old", "placed"])
def test_an_adoption_cut_short_is_finished_by_the_next_start(tmp_path, cut_after):
    """BAK-5: a power cut between the steps used to leave a service that never started again."""
    pending = _home(tmp_path)
    real_write = pending_import.write_json
    calls = {"n": 0}

    def cut(path, data):
        real_write(path, data)
        if path.name == "plan.json" and data.get(cut_after):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("power cut")

    pending_import.write_json = cut
    try:
        with pytest.raises(OSError):
            pending_import.apply(tmp_path)
    finally:
        pending_import.write_json = real_write
    assert pending_import.apply(tmp_path) == "work"  # the next start finishes the job
    assert (tmp_path / "data" / "hotel.db").read_bytes() == b"the hotel"
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["role"] == "reception"
    [kept] = (tmp_path / "backups").glob("pre-import-*")
    assert (kept / "hotel.db").read_bytes() == b"empty install"
    assert json.loads((pending / "plan.json").read_text(encoding="utf-8"))["applied"] is True


def test_a_damaged_owner_database_is_not_mistaken_for_an_empty_pc(tmp_path):
    """BAK-7: a corrupt file used to count as «no accounts» and turned the owner PC into a reception PC."""
    (tmp_path / "config.json").write_text(
        json.dumps({"role": "owner", "hotel_id": "5a7e0000-0000-4000-8000-000000000001"}), encoding="utf-8"
    )
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "hotel.db").write_bytes(b"SQLite format 3\x00" + b"\xff" * 200)
    assert runtime.users_in_database(tmp_path / "data" / "hotel.db") is None
    assert runtime.promote_empty_owner(tmp_path) is False
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["role"] == "owner"


def test_the_log_file_handler_is_attached_once_and_again_after_django_resets_logging(tmp_path):
    root = logging.getLogger()
    run_waitress._log_to_file(tmp_path)
    run_waitress._log_to_file(tmp_path)
    ours = [h for h in root.handlers if getattr(h, "baseFilename", "").endswith("server.log")]
    assert len(ours) == 1
    root.removeHandler(ours[0])  # what settings.LOGGING does at django.setup()
    run_waitress._log_to_file(tmp_path)
    assert ours[0] in root.handlers
    root.removeHandler(ours[0])
    ours[0].close()
