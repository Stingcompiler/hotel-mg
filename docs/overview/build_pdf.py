"""Print docs/overview/overview.ar.html to docs/SkyTowers-Overview-ar.pdf with headless Microsoft Edge.

Edge shapes Arabic and lays out right-to-left correctly (the page's own fonts, A4, backgrounds kept), which the
Python PDF libraries do not. Windows only. Run from the repo root:

    python docs/overview/build_pdf.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs" / "overview" / "overview.ar.html"
TARGET = ROOT / "docs" / "SkyTowers-Overview-ar.pdf"
EDGE = [
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
]


def main() -> int:
    edge = next((p for p in EDGE if p.exists()), None)
    if edge is None:
        print("Microsoft Edge not found")
        return 1
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [
                str(edge),
                "--headless=new",
                "--disable-gpu",
                "--no-pdf-header-footer",
                "--virtual-time-budget=10000",
                f"--user-data-dir={profile}",
                f"--print-to-pdf={TARGET}",
                SOURCE.as_uri(),
            ],
            check=True,
            timeout=180,
        )
    print(f"{TARGET} ({TARGET.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
