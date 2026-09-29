"""Who holds 127.0.0.1:8471? (Track W.) The port is the service's by design (spec §2), so an installer or a
service start that finds another process on it — typically a server started from a source checkout — may end
that process. Our own executable is never killed (a second install, a console `run`).

Windows-only in effect: on other systems the helpers report nothing and do nothing.
"""

import logging
import re
import subprocess
import sys

OWN_IMAGES = ("skytowers-server.exe",)
# Only a server started from a source checkout is ever ended; anything else is reported, not killed (E-13).
DEV_IMAGES = ("python.exe", "pythonw.exe", "py.exe")
log = logging.getLogger(__name__)


def parse_netstat(text: str, port: int) -> int | None:
    """PID of the process listening on the port from ``netstat -ano -p tcp`` output, else None.

    A listening row has no remote end (``0.0.0.0:0`` / ``[::]:0``); the state word is not matched because Windows
    translates it (review 2026-09-29, E-13)."""
    pattern = re.compile(
        rf"^\s*TCP\s+(?:127\.0\.0\.1|0\.0\.0\.0|\[::1?\]):{port}\s+(?:0\.0\.0\.0:0|\[::\]:0)\s+\S+\s+(\d+)\s*$",
        re.M,
    )
    match = pattern.search(text)
    return int(match.group(1)) if match else None


def parse_tasklist(text: str) -> str | None:
    """Image name from ``tasklist /FO CSV /NH`` for one PID, else None."""
    match = re.search(r'^"([^"]+)","(\d+)"', text, re.M)
    return match.group(1) if match else None


def _run(args: list[str]) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=15, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def listener(port: int) -> tuple[int, str] | None:
    """(pid, image name) of the process listening on the port, or None when free or not on Windows."""
    if not sys.platform.startswith("win"):
        return None
    pid = parse_netstat(_run(["netstat", "-ano", "-p", "tcp"]), port)
    if pid is None:
        return None
    image = parse_tasklist(_run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"])) or "?"
    return pid, image


def describe(port: int) -> str:
    holder = listener(port)
    return f"port {port} is held by PID {holder[0]} ({holder[1]})" if holder else f"port {port} is free"


def free_port(port: int) -> str:
    """End a foreign listener on the port; our own executable stays. Returns a one-line report."""
    holder = listener(port)
    if holder is None:
        return f"port {port} is free"
    pid, image = holder
    if image.lower() in OWN_IMAGES:
        return f"port {port} is held by our own {image} (PID {pid}); left alone"
    if image.lower() not in DEV_IMAGES:
        log.error("port %s is held by %s (PID %s); not ended — close that program", port, image, pid)
        return f"port {port} is held by {image} (PID {pid}); not ended"
    _run(["taskkill", "/PID", str(pid), "/F"])
    log.warning("ended %s (PID %s), which held port %s that belongs to the Sky Towers service", image, pid, port)
    return f"ended {image} (PID {pid}) which held port {port}"
