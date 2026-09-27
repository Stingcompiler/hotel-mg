"""Serve the API and the SPA with Waitress on 127.0.0.1:8471 (spec §2).

The settings module follows ``role`` in config.json, so one build serves both PCs. The scheduler thread
(alert engine, clock guard, scheduled backups) runs next to the server on the reception PC.

    python -m service.run_waitress          # from server/ (development)
    skytowers-server.exe run                # the Windows bundle, in a console
"""

import logging
import logging.handlers
import os
import socket
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

    import django
    from django.core.management import call_command

    django.setup()
    # After django.setup(): settings.LOGGING replaces the root handlers, so a file handler added
    # earlier is dropped and server.log stays empty.
    _log_to_file(cfg.home / "logs")
    # Updates: a newer build migrates the database on its first start (spec §11).
    call_command("migrate", interactive=False, verbosity=0)
    if cfg.role == "reception":
        # A new install opens on the login page with the default owner account, never a setup form.
        from apps.accounts.services import ensure_default_owner

        ensure_default_owner()
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


def listen_socket(host: str = HOST, port: int = PORT) -> socket.socket:
    """The listening socket, bound exclusively. Waitress's own bind sets SO_REUSEADDR, which on Windows lets a
    second server bind the same port beside the service and take part of its requests (found with a source
    checkout running next to an installed owner PC). SO_EXCLUSIVEADDRUSE makes that second bind fail instead,
    so the port guard below sees the conflict."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:  # POSIX: reuse only skips TIME_WAIT; a live listener still refuses the bind
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
    except OSError:
        sock.close()
        raise
    return sock


def create_server():
    """The Waitress server with the scheduler started; ``.run()`` blocks, ``.close()`` stops (Windows service)."""
    role = setup_django()

    from django.conf import settings
    from waitress import create_server as waitress_server

    from config.wsgi import application
    from service import scheduler

    log = logging.getLogger(__name__)
    if not (settings.SPA_ROOT / "index.html").is_file():
        log.error(
            "SPA missing: %s has no index.html — the app window will show «واجهة البرنامج غير مبنية بعد»",
            settings.SPA_ROOT,
        )
    try:
        sock = listen_socket()
    except OSError as e:
        # The port is ours by design (spec §2): end a foreign holder (a server run from a source
        # checkout) and retry once.
        from service import port

        log.error("cannot listen on %s:%s (%s) — %s", HOST, PORT, e, port.describe(PORT))
        log.warning(port.free_port(PORT))
        sock = listen_socket()
    server = waitress_server(application, sockets=[sock], threads=THREADS)
    if role == "reception":  # the owner PC has no hotel operations to watch
        scheduler.start()
    log.info(
        "Sky Towers server (%s) on http://%s:%s · SPA %s · exe %s", role, HOST, PORT, settings.SPA_ROOT, sys.executable
    )
    return server


def stop(server) -> None:
    """Stop serving, from another thread (the Windows service's stop request).

    Closing only the listener left Waitress's loop running while any keep-alive connection stayed open, and the
    app window polls every 30 s, so the service hung in STOP_PENDING (upgrades, reset_data and restore_full need
    it stopped). Every channel is closed inside the loop's own thread through the trigger; the map empties and
    ``run()`` returns.
    """

    def close_all() -> None:
        for channel in list(server._map.values()):
            try:
                channel.close()
            except OSError:
                pass

    server.trigger.pull_trigger(close_all)


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()
