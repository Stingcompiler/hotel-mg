from datetime import UTC, datetime, timedelta

from apps.backup import rules


def test_manifest_round_trip_and_mismatch():
    files = {"hotel.db": b"db", "attachments/a.jpg": b"img"}
    manifest = rules.build_manifest(
        hotel_id="h",
        seq=3,
        created_at=datetime(2026, 9, 26, tzinfo=UTC),
        schema_version=1,
        app_version="0.1.0",
        migrations={"stays.0001"},
        full=True,
        audit_seq=10,
        files=files,
    )
    assert rules.mismatched_files(manifest, files) == []
    assert rules.mismatched_files(manifest, {**files, "hotel.db": b"DB"}) == ["hotel.db"]
    assert rules.mismatched_files(manifest, {"hotel.db": b"db"}) == ["attachments/a.jpg"]
    assert b'"seq": 3' in rules.manifest_bytes(manifest)
    assert rules.check("hotel", "معرف الفندق", "5a7e0000", "ok")["label"] == "معرف الفندق"


def test_stale_hours():
    now = datetime(2026, 9, 26, 16, 0, tzinfo=UTC)
    assert rules.stale_hours(None, now, 24) is None
    assert rules.stale_hours(now - timedelta(hours=23, minutes=59), now, 24) is None
    assert rules.stale_hours(now - timedelta(hours=26, minutes=30), now, 24) == 26
