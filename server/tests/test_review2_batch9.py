"""Review 2026-09-29, batch 9: updates and the Windows service (E-5, E-12, E-13)."""

from unittest import mock

import pytest
from django.db import OperationalError

from service import port

ARABIC_NETSTAT = """
الاتصالات النشطة

  البروتوكول  العنوان المحلي          العنوان الخارجي        الحالة           PID
  TCP    127.0.0.1:8471         0.0.0.0:0              يستمع            4242
  TCP    127.0.0.1:8471         127.0.0.1:50123        تم التأسيس       4242
"""


def test_the_port_guard_reads_a_translated_netstat():
    """E-13: the state word («LISTENING») is translated on Arabic Windows; the listening row is found by address."""
    assert port.parse_netstat(ARABIC_NETSTAT, 8471) == 4242
    assert port.parse_netstat(ARABIC_NETSTAT, 9999) is None


def test_the_port_guard_ends_only_a_development_server():
    with (
        mock.patch.object(port, "listener", return_value=(4242, "SomeOtherApp.exe")),
        mock.patch.object(port, "_run") as run,
    ):
        assert "not ended" in port.free_port(8471)
        run.assert_not_called()
    with (
        mock.patch.object(port, "listener", return_value=(4243, "python.exe")),
        mock.patch.object(port, "_run") as run,
    ):
        assert port.free_port(8471).startswith("ended python.exe")
        run.assert_called_once()


@pytest.mark.django_db
def test_a_full_disk_is_a_clear_message(reception_api):
    """E-12: SQLite «database or disk is full» was a generic 500."""
    with mock.patch("apps.core.views.HotelSettings.load", side_effect=OperationalError("database or disk is full")):
        res = reception_api.get("/api/v1/system/settings")
    assert res.status_code == 507 and res.json()["code"] == "disk_full"


@pytest.mark.django_db
def test_the_service_knows_a_database_made_by_a_newer_version():
    """E-5: an older build must not run on a database a newer version migrated."""
    from django.db import connection
    from django.db.migrations.recorder import MigrationRecorder

    from service import run_waitress

    assert run_waitress.newer_database() == []
    MigrationRecorder(connection).record_applied("billing", "9999_from_the_future")
    assert run_waitress.newer_database() == ["billing.9999_from_the_future"]


@pytest.mark.django_db
def test_the_installer_updates_the_database_and_reads_the_result(capsys):
    """E-4: ``upgrade-db`` exit codes — 0 updated, 3 failed (rolled back by the installer), 4 newer database."""
    from django.db import connection
    from django.db.migrations.recorder import MigrationRecorder

    from service import cli

    assert cli.main(["upgrade-db"]) == 0
    with mock.patch("django.core.management.call_command", side_effect=RuntimeError("boom")):
        assert cli.upgrade_db() == 3
    assert "boom" in capsys.readouterr().out
    MigrationRecorder(connection).record_applied("billing", "9999_from_the_future")
    assert cli.upgrade_db() == 4


# NSIS constants and variables the installer hooks may use. NSIS keeps an unknown ``$NAME`` as literal text (only a
# build warning): «$COMMONAPPDATA» made every data-folder step of 1.0–1.1.8 act on a folder that does not exist.
NSIS_NAMES = {"$INSTDIR", "$APPDATA", "$LOCALAPPDATA", "$TEMP", "$PROGRAMFILES", "$SkytPre", "$SkytPrev"}


def test_the_installer_hooks_use_only_known_nsis_names():
    import re
    from pathlib import Path

    hooks = Path(__file__).resolve().parents[2] / "desktop/src-tauri/windows/hooks.nsh"
    code = "\n".join(
        line for line in hooks.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith(";")
    )
    used = set(re.findall(r"(?<!\$)\$[A-Za-z_]\w*", code))
    assert used <= NSIS_NAMES, used - NSIS_NAMES
    assert r'!define SKYT_DATA "$APPDATA\SkyTowers"' in code
