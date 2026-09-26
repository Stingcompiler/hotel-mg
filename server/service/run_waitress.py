"""Serve the API and the SPA with Waitress on 127.0.0.1:8471 (spec §2).

The settings module follows ``role`` in config.json, so one build serves both PCs. The scheduler thread
(alert engine, clock guard, scheduled backups) runs next to the server on the reception PC.

    python -m service.run_waitress          # from server/ (development)
    skytowers-server.exe run                # the Windows bundle, in a console
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8471
THREADS = 8


def setup_django() -> str:
    """Pick the settings from config.json, configure logging to the data folder, run migrations. Returns the role."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from config import runtime

    cfg = runtime.load()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"config.settings.{cfg.role}")
    _log_to_file(cfg.home / "logs")

    import django
    from django.core.management import call_command

    django.setup()
    # Updates: a newer build migrates the database on its first start (spec §11).
    call_command("migrate", interactive=False, verbosity=0)
    if cfg.role == "owner":
        # The owner's backup key is made on the first start; the login page shows its public half.
        from apps.backup import keys

        keys.generate()
    return cfg.role


def _log_to_file(folder: Path) -> None:
    """``<home>/logs/server.log`` (the desktop fallback page's «فتح سجل الأخطاء»), 5 × 2 MB."""
    folder.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        folder / "server.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def create_server():
    """The Waitress server with the scheduler started; ``.run()`` blocks, ``.close()`` stops (Windows service)."""
    role = setup_django()

    from waitress import create_server as waitress_server

    from config.wsgi import application
    from service import scheduler

    if role == "reception":  # the owner PC has no hotel operations to watch
        scheduler.start()
    logging.getLogger(__name__).info("Sky Towers server (%s) on http://%s:%s", role, HOST, PORT)
    return waitress_server(application, host=HOST, port=PORT, threads=THREADS)


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()
