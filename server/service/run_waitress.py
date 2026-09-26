"""Serve the API with Waitress on 127.0.0.1:8471 (spec §2).

The settings module follows ``role`` in config.json, so one build serves both PCs.
The Windows service wrapper (pywin32) and the scheduler thread arrive in Track W / B3.

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

    serve(application, host=HOST, port=PORT, threads=8)


if __name__ == "__main__":
    main()
