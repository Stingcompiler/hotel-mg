"""A refused event-log write must not stop the service from starting (decision 238)."""

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="pywin32 service module")


def test_report_started_survives_a_refused_event_log(monkeypatch, caplog):
    import pywintypes

    from service import win_service

    def refuse(*args):
        raise pywintypes.error(5, "RegisterEventSource/ReportEvent", "Access is denied.")

    monkeypatch.setattr(win_service.servicemanager, "LogMsg", refuse)
    win_service.report_started("SkyTowersServer")  # no exception
    assert "could not write" in caplog.text
