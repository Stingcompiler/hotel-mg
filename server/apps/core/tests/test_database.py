"""SQLite connection settings required by spec §3."""

import copy

import pytest
from django.db import connection, connections


def _pragma(conn, name):
    with conn.cursor() as cursor:
        cursor.execute(f"PRAGMA {name}")
        return cursor.fetchone()[0]


@pytest.mark.django_db
def test_connection_pragmas():
    assert _pragma(connection, "foreign_keys") == 1
    assert _pragma(connection, "synchronous") == 2  # FULL
    assert _pragma(connection, "busy_timeout") == 20000
    assert connection.transaction_mode == "IMMEDIATE"


@pytest.mark.django_db
def test_file_database_uses_wal(tmp_path):
    # The test database is in-memory, which cannot use WAL; open a real file with the same settings.
    default = connections["default"]
    settings_dict = copy.deepcopy(default.settings_dict)
    settings_dict["NAME"] = str(tmp_path / "hotel.db")
    wrapper = type(default)(settings_dict, alias="wal_check")
    try:
        wrapper.ensure_connection()
        assert _pragma(wrapper, "journal_mode") == "wal"
    finally:
        wrapper.close()
