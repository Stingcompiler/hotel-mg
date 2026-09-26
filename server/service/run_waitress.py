"""Serve the API with Waitress on 127.0.0.1:8471 (spec §2).

The settings module follows ``role`` in config.json, so one build serves both PCs.
The scheduler thread (alert engine, clock guard) runs next to the server; the pywin32 service wrapper is Track W.

    python -m service.run_waitress          # from server/
"""

import os
import sys
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8471


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from config import runtime

    role = runtime.load().role
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"config.settings.{role}")

    import django
    from django.core.management import call_command

    django.setup()
    call_command("migrate", interactive=False, verbosity=0)

    from waitress import serve

    from config.wsgi import application
    from service import scheduler

    if role == "reception":  # the owner PC has no hotel operations to watch
        scheduler.start()

    serve(application, host=HOST, port=PORT, threads=8)


if __name__ == "__main__":
    main()
