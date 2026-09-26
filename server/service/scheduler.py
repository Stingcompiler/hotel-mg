"""Background thread in the service process: alert engine and clock guard every 60 s (spec §2).

Scheduled backups join this loop in phase B4.
"""

import logging
import threading

log = logging.getLogger(__name__)

INTERVAL_SECONDS = 60


def _loop(stop: threading.Event) -> None:
    from django.db import close_old_connections

    from apps.followups import engine

    while not stop.is_set():
        try:
            close_old_connections()
            result = engine.tick()
            if result.get("blocked"):
                log.warning("Clock rollback: writes blocked until a manager approves")
        except Exception:  # keep the scheduler alive; the next tick retries
            log.exception("Engine tick failed")
        stop.wait(INTERVAL_SECONDS)


def start() -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=_loop, args=(stop,), name="skytowers-scheduler", daemon=True).start()
    return stop
