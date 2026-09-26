# PyInstaller spec for the Windows service bundle (Track W, spec §3): one folder, console subsystem.
#     cd server && pyinstaller ../build/windows/skytowers-server.spec --distpath ../dist-server --workpath ../build-work
# The SPA must be built first (python build/build_spa.py): it ships inside the bundle as static_spa/.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

SERVER = Path(SPECPATH).resolve().parent.parent / "server"

hidden = []
for package in ("apps", "config", "service", "rest_framework", "drf_spectacular", "django.contrib"):
    hidden += collect_submodules(package)
hidden += ["win32timezone", "waitress", "openpyxl", "pyrage", "googleapiclient", "google_auth_oauthlib"]

datas = []
for package in ("django", "rest_framework", "drf_spectacular"):
    datas += collect_data_files(package)
datas += [(str(SERVER / "static_spa"), "static_spa")]

a = Analysis(
    [str(SERVER / "service" / "cli.py")],
    pathex=[str(SERVER)],
    hiddenimports=hidden,
    datas=datas,
    excludes=["pytest", "hypothesis", "tkinter"],
    noarchive=False,
)
# googleapiclient's hook ships ~100 MB of discovery documents; the service only talks to Drive v3.
a.datas = [
    entry
    for entry in a.datas
    if "discovery_cache/documents/" not in entry[0].replace("\\", "/") or entry[0].endswith("drive.v3.json")
]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="skytowers-server",
    console=True,
    icon=str(SERVER.parent / "desktop" / "src-tauri" / "icons" / "icon.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="skytowers-server")
