"""Windows service «SkyTowersServer» (spec §2, Track W): Waitress + scheduler, started before login.

Installed by the NSIS hooks with ``skytowers-server.exe install``; runs as LocalSystem with data in
``%ProgramData%\\SkyTowers``. Only imported on Windows (pywin32).
"""

import servicemanager
import win32event
import win32service
import win32serviceutil

SERVICE_NAME = "SkyTowersServer"


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
            self.server.close()
        win32event.SetEvent(self.stopped)

    def SvcDoRun(self):  # noqa: N802 (pywin32 API)
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE, servicemanager.PYS_SERVICE_STARTED, (self._svc_name_, "")
        )
        from service import run_waitress

        self.server = run_waitress.create_server()
        try:
            self.server.run()
        except OSError:  # close() during run() on stop
            pass


def dispatch() -> None:
    """Called when the Service Control Manager starts the executable without arguments."""
    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(SkyTowersService)
    servicemanager.StartServiceCtrlDispatcher()


def handle_command_line(argv: list[str]) -> None:
    """``install`` / ``start`` / ``stop`` / ``remove`` / ``--startup auto install``."""
    win32serviceutil.HandleCommandLine(SkyTowersService, argv=argv)
