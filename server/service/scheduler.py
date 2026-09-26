"""Background thread in the service process (spec §2): every 60 s the clock guard and alert engine,
then a scheduled backup when one is due (spec §9.1, default every 6 h)."""

import logging
import threading

log = logging.getLogger(__name__)

INTERVAL_SECONDS = 60


def _loop(stop: threading.Event) -> None:
    from django.db import close_old_connections

    from apps.backup import drive, export
    from apps.followups import engine

    while not stop.is_set():
        try:
            close_old_connections()
            result = engine.tick()
            if result.get("blocked"):
                log.warning("Clock rollback: writes blocked until a manager approves")
            else:
                run = export.run_if_due()
                if run is not None and run.status == "failed":
                    log.error("Scheduled backup failed: %s", run.message)
                drive.upload_if_due()  # silently retried every 10 minutes while offline
        except Exception:  # keep the scheduler alive; the next tick retries
            log.exception("Engine tick failed")
        stop.wait(INTERVAL_SECONDS)


def start() -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=_loop, args=(stop,), name="skytowers-scheduler", daemon=True).start()
    return stop
