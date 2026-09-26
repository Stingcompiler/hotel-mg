import uuid
from datetime import UTC, datetime

import pytest
from django.db import connection, transaction

from apps.audit import rules, services
from apps.audit.models import AuditLog

AT = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)


def _payload(seq, **over):
    base = {
        "seq": seq, "hotel_id": "h", "actor_id": None, "action": "a", "entity": "e",
        "entity_id": "1", "before": None, "after": {"x": 1}, "at": AT,
    }  # fmt: skip
    return {**base, **over}


def _chain(n):
    rows, prev = [], rules.GENESIS_HASH
    for seq in range(1, n + 1):
        payload = _payload(seq)
        h = rules.chain_hash(prev, payload)
        rows.append({**payload, "prev_hash": prev, "hash": h})
        prev = h
    return rows


def test_canonical_json_is_stable_and_keeps_arabic():
    text = rules.canonical_json({"b": 1, "a": "غرفة 203", "t": AT})
    assert text == '{"a":"غرفة 203","b":1,"t":"2026-09-26T08:00:00+00:00"}'


def test_canonical_json_writes_uuids_as_text():
    value = uuid.UUID("5a7e0000-0000-4000-8000-000000000001")
    assert rules.canonical_json({"id": value}) == '{"id":"5a7e0000-0000-4000-8000-000000000001"}'


def test_canonical_json_rejects_unknown_types():
    with pytest.raises(TypeError):
        rules.canonical_json({"x": object()})


def test_chain_hash_depends_on_previous_hash():
    assert rules.chain_hash("a" * 64, _payload(1)) != rules.chain_hash("b" * 64, _payload(1))


def test_first_broken_accepts_valid_chain():
    assert rules.first_broken(_chain(4)) is None
    assert rules.first_broken([]) is None


def test_first_broken_detects_tampering():
    rows = _chain(4)
    rows[2]["after"] = {"x": 999}
    assert rules.first_broken(rows) == 3


def test_first_broken_detects_gap_and_relinking():
    rows = _chain(4)
    assert rules.first_broken(rows[:1] + rows[2:]) == 3
    rows = _chain(3)
    rows[1]["prev_hash"] = "f" * 64
    assert rules.first_broken(rows) == 2


@pytest.mark.django_db(transaction=True)  # no wrapping test transaction
def test_record_requires_transaction():
    with pytest.raises(RuntimeError):
        services.record(actor=None, action="x", entity="y")


@pytest.mark.django_db
class TestRecord:
    def test_rows_form_a_verified_chain(self, reception):
        with transaction.atomic():
            first = services.record(actor=reception, action="room.set_status", entity="room", entity_id="203",
                                    before={"status": "ready"}, after={"status": "occupied"})  # fmt: skip
        with transaction.atomic():
            second = services.record(actor=None, action="system.x", entity="system", after={"n": 1})
        assert (first.seq, second.seq) == (1, 2)
        assert first.prev_hash == rules.GENESIS_HASH
        assert second.prev_hash == first.hash
        assert services.verify_chain() is None

    def test_verify_finds_row_edited_in_database(self):
        for i in range(3):
            with transaction.atomic():
                services.record(actor=None, action="x", entity="e", entity_id=str(i), after={"v": i})
        with connection.cursor() as cursor:  # bypass the ORM's append-only guard, like a hand edit would
            cursor.execute(f"UPDATE {AuditLog._meta.db_table} SET after = %s WHERE seq = 2", ['{"v": 42}'])
        assert services.verify_chain() == 2

    def test_snapshot_drops_secrets(self, reception):
        snap = services.snapshot(reception)
        assert "password" not in snap and "pin_hash" not in snap
        assert snap["username"] == "ahmed.ali"
        assert snap["id"] == str(reception.pk)


@pytest.mark.django_db
class TestAuditApi:
    def test_list_is_manager_only(self, reception_api, manager_api):
        assert reception_api.get("/api/v1/audit/").status_code == 403
        res = manager_api.get("/api/v1/audit/")
        assert res.status_code == 200
        actions = [row["action"] for row in res.json()["results"]]
        assert "auth.login_password" in actions

    def test_filter_by_entity(self, manager_api, manager):
        res = manager_api.get("/api/v1/audit/", {"entity": "user", "id": str(manager.pk)})
        assert {row["entity_id"] for row in res.json()["results"]} == {str(manager.pk)}

    def test_verify(self, manager_api):
        res = manager_api.get("/api/v1/audit/verify")
        assert res.json()["ok"] is True
        assert res.json()["first_broken_seq"] is None
