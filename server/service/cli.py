"""``skytowers-server.exe`` — the PyInstaller entry point (Track W).

skytowers-server.exe run                          # serve in this console (debugging)
skytowers-server.exe init --role reception        # installer: write config.json once
skytowers-server.exe init --role reception --force # switch this PC's role (config.json rewritten, data kept)
skytowers-server.exe manage <command> [args]      # Django management (migrate, backup_now, …)
skytowers-server.exe upgrade-db                   # installer: update the database now (0 ok, 4 newer, 3 failed)
skytowers-server.exe free-port                    # installer: end a foreign process holding 127.0.0.1:8471
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


def upgrade_db() -> int:
    """The installer updates the database itself, so a failure is seen and undone there instead of a service
    restarting for ever (review 2026-09-29, E-4). 4: the database belongs to a newer version (E-5)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from config import runtime

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"config.settings.{runtime.load().role}")
    import django

    django.setup()
    from django.core.management import call_command

    from service import run_waitress

    newer = run_waitress.newer_database()
    if newer:
        print("the database belongs to a newer Sky Towers: " + ", ".join(newer))
        return 4
    try:
        call_command("migrate", interactive=False, verbosity=1)
    except Exception as exc:  # noqa: BLE001 — any failure is reported to the installer by the exit code
        print(f"database update failed: {exc!r}")
        return 3
    return 0


def _utf8_console() -> None:
    """Arabic messages must not crash a cp1252 console or the installer's captured output."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _utf8_console()
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0] if argv else ""

    if command == "run":
        from service import run_waitress

        run_waitress.main()
        return 0
    if command == "init":
        from config import runtime

        role = argv[argv.index("--role") + 1] if "--role" in argv else "reception"
        written = runtime.init_config(runtime.default_home(), role, force="--force" in argv)
        print(f"config.json written (role {role})" if written else "config.json kept (existing install)")
        return 0
    if command == "manage":
        _django_manage(argv[1:])
        return 0
    if command == "upgrade-db":
        return upgrade_db()
    if command == "free-port":
        from service import port, run_waitress

        print(port.free_port(run_waitress.PORT))
        return 0

    from service import win_service  # Windows only

    if not argv:
        win_service.dispatch()
    else:
        win_service.handle_command_line([sys.argv[0], *argv])
    return 0


if __name__ == "__main__":
    sys.exit(main())
