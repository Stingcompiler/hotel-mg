"""Build the SPA and copy it next to the Django service (spec §2 ``server/static_spa``, F3).

    python build/build_spa.py            # npm run build in web/, then copy web/dist → server/static_spa
    python build/build_spa.py --no-build # copy an existing web/dist only

Works on Windows and Linux; needs Node 20+ on PATH for the build step.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DIST = WEB / "dist"
TARGET = ROOT / "server" / "static_spa"


def main() -> int:
    if "--no-build" not in sys.argv:
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm:
            print("npm not found: install Node.js 20+ first.", file=sys.stderr)
            return 1
        if not (WEB / "node_modules").is_dir():
            subprocess.run([npm, "ci"], cwd=WEB, check=True)
        subprocess.run([npm, "run", "build"], cwd=WEB, check=True)
    if not (DIST / "index.html").is_file():
        print(f"No build in {DIST}.", file=sys.stderr)
        return 1
    if TARGET.exists():
        shutil.rmtree(TARGET)
    shutil.copytree(DIST, TARGET)
    print(f"SPA copied to {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
