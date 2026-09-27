"""Windows service «SkyTowersServer» (spec §2, Track W): Waitress + scheduler, started before login.

Installed by the NSIS hooks with ``skytowers-server.exe install``; runs as LocalSystem with data in
``%ProgramData%\\SkyTowers``. Only imported on Windows (pywin32).
"""

import os
import threading

import servicemanager
import win32event
import win32service
import win32serviceutil

SERVICE_NAME = "SkyTowersServer"
# A stop must end: upgrades, reset_data and restore_full wait for the database to be free.
STOP_GRACE_SECONDS = 20


class SkyTowersService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = "Sky Towers Server"
    _svc_description_ = "خادم نظام إدارة فندق سكاي تاورز المحلي (127.0.0.1:8471)."

    def __init__(self, args):
        super().__init__(args)
        self.stopped = win32event.CreateEvent(None, 0, 0, None)
        self.server = None

    def SvcStop(self):  # noqa: N802 (pywin32 API)
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.server is not None:
            from service import run_waitress

            run_waitress.stop(self.server)  # also closes the app window's keep-alive connections
        win32event.SetEvent(self.stopped)
        timer = threading.Timer(STOP_GRACE_SECONDS, self._force_exit)
        timer.daemon = True
        timer.start()

    def _force_exit(self):
        """Last resort when the loop did not end in time: SQLite (WAL) keeps committed data across an exit."""
        self.ReportServiceStatus(win32service.SERVICE_STOPPED)
        os._exit(0)

    def SvcDoRun(self):  # noqa: N802 (pywin32 API)
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE, servicemanager.PYS_SERVICE_STARTED, (self._svc_name_, "")
        )
        from service import run_waitress

        self.server = run_waitress.create_server()
        try:
            self.server.run()
        except OSError:  # a socket closed during stop
            pass
        self.server.task_dispatcher.shutdown(timeout=5)


def dispatch() -> None:
    """Called when the Service Control Manager starts the executable without arguments."""
    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(SkyTowersService)
    servicemanager.StartServiceCtrlDispatcher()


def handle_command_line(argv: list[str]) -> None:
    """``install`` / ``start`` / ``stop`` / ``remove`` / ``--startup auto install``."""
    win32serviceutil.HandleCommandLine(SkyTowersService, argv=argv)
