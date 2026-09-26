"""Spec §12 B4 gate: three sequential imports reproduce reception totals; repeat import is a no-op;
corrupt/foreign file rejected with no side effects; owner role refuses every mutation."""

import dataclasses
import uuid
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.backup import export, keys, merge, rules
from apps.backup.models import ImportRun
from apps.billing import services as billing
from apps.cash import services as cash
from apps.guests.models import Guest
from apps.reports.totals import snapshot
from apps.rooms.models import Room, RoomType
from apps.stays import services as reservations
from apps.stays import stay_services

pytestmark = pytest.mark.django_db(transaction=True, databases=["default", "owner", "incoming"])


@pytest.fixture
def owner_identity(tmp_path):
    path = tmp_path / "owner.key"
    public = keys.generate(path)
    return keys.load(path), public


@pytest.fixture
def hotel(owner_identity, tmp_path, monkeypatch):
    """Reception with rooms, a manager, an open shift and backups encrypted to the owner key."""
    monkeypatch.setattr(settings, "RUNTIME", dataclasses.replace(settings.RUNTIME, home=tmp_path / "reception"))
    settings.RUNTIME.data_dir.mkdir(parents=True, exist_ok=True)
    manager = User.objects.create_user("manager", "المدير", role="manager", password="pw-123456", pin="1234")
    double = RoomType.objects.create(
        name="مزدوجة", nightly_price=1_500_000, weekly_price=9_500_000, monthly_price=30_000_000
    )
    for n in ("201", "202", "203", "204"):
        Room.objects.create(number=n, floor=2, room_type=double)
    cfg = export.backup_settings()
    cfg.owner_recipient = owner_identity[1]
    cfg.save()
    cash.open_shift(manager, opening=5_000_000)
    return manager


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


def test_backup_file_is_encrypted_and_complete(hotel, owner_identity):
    walk_in(hotel, "201", "محمد عثمان الطيب", pay=1_000_000)
    path = backup(hotel)
    raw = path.read_bytes()
    assert raw.startswith(b"age-encryption.org/v1")
    assert path.name.startswith("skytowers-5a7e0000-000001-")
    manifest, files = merge._open(raw, owner_identity[0])
    assert manifest["seq"] == 1 and manifest["full"] is True
    assert rules.DB_FILE in files and not rules.mismatched_files(manifest, files)
    assert any(m.startswith("stays.") for m in manifest["migrations"])


def test_scheduled_backup_skips_when_nothing_changed(hotel):
    first = export.run_backup(kind="scheduled")
    assert first.status == "ok"
    second = export.run_backup(kind="scheduled")
    assert second.status == "skipped" and second.message == "لا تغييرات منذ آخر نسخة"
    walk_in(hotel, "201", "محمد عثمان")
    assert export.run_backup(kind="scheduled").status == "ok"


def test_retention_and_second_folder(hotel, tmp_path):
    cfg = export.backup_settings()
    cfg.keep_count, cfg.second_dir = 2, str(tmp_path / "usb")
    cfg.save()
    for i in range(4):
        walk_in(hotel, f"20{i + 1}", f"نزيل رقم {i}")
        backup(hotel)
    assert len(list(settings.RUNTIME.backups_dir.glob("*.age"))) == 2
    assert len(list((tmp_path / "usb").glob("*.age"))) == 2
    cfg.second_dir = "/proc/not-writable/usb"
    cfg.save()
    run = export.run_backup(hotel)
    assert run.status == "ok" and run.second_error.startswith("المجلد الثاني غير متاح")


def test_missing_owner_key_fails_visibly(hotel):
    cfg = export.backup_settings()
    cfg.owner_recipient = ""
    cfg.save()
    run = export.run_backup(hotel)
    assert run.status == "failed" and "مفتاح المالك" in run.message


def test_three_sequential_imports_reproduce_reception_totals(hotel, owner_identity):
    identity = owner_identity[0]
    first = walk_in(hotel, "201", "محمد عثمان الطيب", pay=1_000_000)
    b1 = backup(hotel)
    walk_in(hotel, "202", "فاطمة أحمد النور", nights=2, pay=3_000_000)
    stay_services.extend(hotel, first.pk, duration_kind="daily", count=2)
    b2 = backup(hotel)
    cash.create_expense(hotel, category="supplies", amount=500_000, note="مواد تنظيف", method="cash")
    billing.record_payment(
        hotel, billing.folio_of(first.reservation).pk, amount=6_500_000, method="bankak", reference="BOK-1"
    )
    stay_services.checkout(hotel, first.pk)
    b3 = backup(hotel)

    results = [do_import(b, identity) for b in (b1, b2, b3)]
    assert [r.run.status for r in results] == ["ok", "ok", "ok"]
    assert snapshot("owner") == snapshot("default")
    assert results[1].counts["الإقامات"]["updated"] >= 1  # the extension updated a reservation
    assert all(c["status"] == "ok" for c in results[2].run.checks)
    assert [c["label"] for c in results[2].run.checks] == [
        "التوقيع",
        "سلامة القاعدة",
        "معرف الفندق",
        "الإصدار",
        "سلسلة التدقيق",
    ]

    # Repeat import is a no-op.
    again = do_import(b3, identity, allow_older=True)
    assert again.run.status == "ok"
    assert all(c["inserted"] == 0 and c["updated"] == 0 for c in again.counts.values())
    assert snapshot("owner") == snapshot("default")


def test_older_file_needs_confirmation_and_never_regresses(hotel, owner_identity):
    identity = owner_identity[0]
    stay = walk_in(hotel, "201", "محمد عثمان")
    b1 = backup(hotel)
    stay_services.extend(hotel, stay.pk, duration_kind="daily", count=1)
    b2 = backup(hotel)
    do_import(b2, identity)
    rejected = do_import(b1, identity)
    assert rejected.run.status == "failed" and rejected.run.error == "هذا الملف أقدم من البيانات الحالية."
    assert rejected.run.checks[-1]["status"] == "warn"
    accepted = do_import(b1, identity, allow_older=True)
    assert accepted.run.status == "ok"
    assert snapshot("owner") == snapshot("default")  # the newer extension was not rolled back


def _rewrite_manifest(path: Path, identity, **changes) -> bytes:
    """A validly signed file whose manifest says something else (e.g. another hotel)."""
    import io
    import json

    import pyrage

    manifest, files = merge._open(path.read_bytes(), identity)
    manifest.update(changes)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(rules.MANIFEST, json.dumps(manifest))
        for name, data in files.items():
            zf.writestr(name, data)
    return pyrage.encrypt(buf.getvalue(), [identity.to_public()])


def _owner_state():
    return snapshot("owner"), ImportRun.objects.using("owner").filter(status="ok").count()


def test_corrupt_and_foreign_files_are_rejected_without_side_effects(hotel, owner_identity, tmp_path):
    identity, _ = owner_identity
    walk_in(hotel, "201", "محمد عثمان")
    good = backup(hotel)
    do_import(good, identity)
    before = _owner_state()

    corrupt = tmp_path / "corrupt.age"
    data = bytearray(good.read_bytes())
    data[len(data) // 2] ^= 0xFF
    corrupt.write_bytes(bytes(data))
    result = do_import(corrupt, identity)
    assert result.run.status == "failed" and result.run.checks[0]["label"] == "التوقيع"

    truncated = tmp_path / "truncated.age"
    truncated.write_bytes(good.read_bytes()[:500])
    assert do_import(truncated, identity).run.status == "failed"

    other_key = keys.load(Path(keys.generate(tmp_path / "other.key")) and tmp_path / "other.key")
    assert do_import(good, other_key).run.status == "failed"  # not encrypted for this owner

    foreign = tmp_path / "foreign.age"
    foreign.write_bytes(_rewrite_manifest(good, identity, hotel_id=str(uuid.uuid4())))
    result = do_import(foreign, identity)
    assert result.run.status == "failed" and result.run.error == "النسخة من فندق آخر."

    assert _owner_state() == before


def test_tampered_audit_chain_is_rejected(hotel, owner_identity):
    from django.db import connection

    from apps.audit.models import AuditLog

    walk_in(hotel, "201", "محمد عثمان")
    with connection.cursor() as cursor:
        cursor.execute(f"UPDATE {AuditLog._meta.db_table} SET action = 'forged' WHERE seq = 2")
    result = do_import(backup(hotel), owner_identity[0])
    assert result.run.status == "failed" and result.run.checks[-1]["label"] == "سلسلة التدقيق"
    assert snapshot("owner")["audit_rows"] == 0


def test_newer_app_version_is_refused(hotel, owner_identity, monkeypatch):
    walk_in(hotel, "201", "محمد عثمان")
    monkeypatch.setattr(merge, "_known_migrations", lambda: {("stays", "0001_initial")})
    result = do_import(backup(hotel), owner_identity[0])
    assert result.run.status == "failed" and "إصدار أحدث" in result.run.error


def test_zip_without_manifest_is_rejected(owner_identity, tmp_path):
    import io

    import pyrage

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hello.txt", "x")
    path = tmp_path / "skytowers-5a7e0000-000009-20260926-1000.age"
    path.write_bytes(pyrage.encrypt(buf.getvalue(), [owner_identity[0].to_public()]))
    result = do_import(path, owner_identity[0])
    assert result.run.status == "failed" and result.run.error.startswith("تعذّر الاستيراد")


def test_owner_role_refuses_every_hotel_write(reception_api, manager):
    endpoints = [
        ("post", "/api/v1/reservations/"),
        ("post", "/api/v1/stays/check-in"),
        ("post", "/api/v1/shifts/open"),
        ("post", "/api/v1/expenses/"),
        ("post", "/api/v1/rooms/"),
        ("patch", "/api/v1/system/settings"),
        ("post", "/api/v1/users/"),
        ("post", "/api/v1/followups/rules"),
        ("post", "/api/v1/backup/run"),
        ("delete", "/api/v1/rooms/00000000-0000-0000-0000-000000000000"),
    ]
    with override_settings(SKYTOWERS_ROLE="owner"):
        for method, url in endpoints:
            res = getattr(reception_api, method)(url, {}, format="json")
            assert res.status_code == 403 and res.json()["code"] == "owner_read_only", url
        assert reception_api.get("/api/v1/rooms/").status_code == 200  # reading is fine
        res = reception_api.post("/api/v1/auth/password", {"username": "manager", "password": "x"}, format="json")
        assert res.json()["code"] == "authentication_failed"  # sign-in is allowed through
        res = reception_api.post("/api/v1/owner/import/run", {}, format="multipart")
        assert res.json()["code"] != "owner_read_only"  # owner/ is let through (then role checks apply)


def test_login_does_not_touch_user_version(manager):
    from apps.accounts.services import login_with_password

    before = User.objects.get(pk=manager.pk)
    login_with_password("manager", "correct-horse")
    after = User.objects.get(pk=manager.pk)
    assert (after.version, after.updated_at) == (before.version, before.updated_at)
    assert after.last_login is not None


def test_backup_api_and_status(hotel):
    from rest_framework.test import APIClient

    from apps.accounts.services import login_with_password

    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Token {login_with_password('manager', 'pw-123456').token}")
    res = api.post("/api/v1/backup/run")
    assert res.status_code == 201 and res.json()["status"] == "ok" and res.json()["kind_label"] == "يدوي"
    assert api.get("/api/v1/backup/runs").json()["results"][0]["seq"] == 1
    assert api.get("/api/v1/system/status").json()["last_backup"] is not None
    cfg = api.get("/api/v1/backup/settings").json()
    bad = api.patch(
        "/api/v1/backup/settings", {"version": cfg["version"], "owner_recipient": "not-a-key"}, format="json"
    )
    assert "owner_recipient" in bad.json()["errors"]
    ok = api.patch("/api/v1/backup/settings", {"version": cfg["version"], "interval_hours": 4}, format="json")
    assert ok.json()["interval_hours"] == 4


def test_run_if_due_and_no_backup_alert(hotel):
    from apps.followups import engine
    from apps.followups.models import FollowupTask

    now = timezone.now()
    assert export.run_if_due(now).status == "ok"
    assert export.run_if_due(now + timedelta(hours=5)) is None
    assert export.run_if_due(now + timedelta(hours=6, minutes=1)) is not None
    engine.tick(now + timedelta(hours=6, minutes=2))
    assert not FollowupTask.objects.filter(rule__trigger_kind="no_backup").exists()
    engine.tick(now + timedelta(hours=31))
    assert FollowupTask.objects.filter(rule__trigger_kind="no_backup").count() == 1


def test_file_name_rules():
    from datetime import datetime

    name = rules.file_name("5a7e0000-0000-4000-8000-000000000001", 118, datetime(2026, 9, 26, 14, 2))
    assert name == "skytowers-5a7e0000-000118-20260926-1402.age"
    assert rules.parse_file_name(name) == ("5a7e0000", 118)
    assert rules.parse_file_name("ST-2026.stbk") is None
    assert rules.parse_file_name("skytowers-a-b-c.age") is None
    assert rules.to_delete(["c", "b", "a"], 2) == ["a"] and rules.to_delete(["a"], 0) == []
    now = timezone.now()
    assert rules.needs_full(None, now) and not rules.needs_full(now - timedelta(days=6), now)
    assert rules.is_due(None, 6, now) and not rules.is_due(now, 6, now) and not rules.is_due(None, 0, now)
    assert rules.unknown_migrations({("stays", "0009_x"), ("other", "1")}, {("stays", "0001")}) == {("stays", "0009_x")}
    assert date.today()  # keep the import used
