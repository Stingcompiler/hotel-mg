"""``skytowers-server.exe`` — the PyInstaller entry point (Track W).

skytowers-server.exe run                          # serve in this console (debugging)
skytowers-server.exe init --role reception        # installer: write config.json once
skytowers-server.exe manage <command> [args]      # Django management (migrate, backup_now, …)
skytowers-server.exe --startup auto install       # Windows service commands (pywin32)
skytowers-server.exe                              # started by the Service Control Manager
"""

import os
import sys
from pathlib import Path


def _django_manage(args: list[str]) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from config import runtime

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"config.settings.{runtime.load().role}")
    from django.core.management import execute_from_command_line

    execute_from_command_line(["skytowers-server", *args])


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0] if argv else ""

    if command == "run":
        from service import run_waitress

        run_waitress.main()
        return 0
    if command == "init":
        from config import runtime

        role = argv[argv.index("--role") + 1] if "--role" in argv else "reception"
        written = runtime.init_config(runtime.default_home(), role)
        print("config.json written" if written else "config.json kept (existing install)")
        return 0
    if command == "manage":
        _django_manage(argv[1:])
        return 0

    from service import win_service  # Windows only

    if not argv:
        win_service.dispatch()
    else:
        win_service.handle_command_line([sys.argv[0], *argv])
    return 0


if __name__ == "__main__":
    sys.exit(main())
