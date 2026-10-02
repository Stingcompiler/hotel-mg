# PyInstaller spec for the Windows service bundle (Track W, spec §3): one folder, console subsystem.
#     cd server && pyinstaller ../build/windows/skytowers-server.spec --distpath ../dist-server --workpath ../build-work
# The SPA must be built first (python build/build_spa.py): it ships inside the bundle as static_spa/.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

SERVER = Path(SPECPATH).resolve().parent.parent / "server"


def source_modules(package):
    """Every module of our own packages, read from the source tree. Django loads settings, apps and
    migrations by name, so PyInstaller cannot see them; collect_submodules() imports them at build time
    and silently drops what fails there (it lost config.settings on windows-latest)."""
    for path in sorted((SERVER / package).rglob("*.py")):
        parts = list(path.relative_to(SERVER).with_suffix("").parts)
        if "tests" in parts:
            continue
        if parts[-1] == "__init__":
            parts = parts[:-1]
        yield ".".join(parts)


hidden = [name for package in ("apps", "config", "service") for name in source_modules(package)]
for package in ("rest_framework", "drf_spectacular", "django.contrib"):
    hidden += collect_submodules(package)
hidden += ["win32timezone", "waitress", "openpyxl", "pyrage", "googleapiclient", "google_auth_oauthlib"]
hidden += ["fpdf", "uharfbuzz", "fontTools.subset", "fontTools.ttLib"]  # report PDFs (shaping is imported lazily)

datas = []
for package in ("django", "rest_framework", "drf_spectacular"):
    datas += collect_data_files(package)
datas += [(str(SERVER / "static_spa"), "static_spa")]
datas += collect_data_files("fpdf")
datas += [(str(SERVER / "apps" / "reports" / "fonts"), "apps/reports/fonts")]  # IBM Plex Sans Arabic for report PDFs

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

# Windows version resource: Explorer › Properties › Details and support tools show which build this is (review
# 2026-09-29, E-22). The number is APP_VERSION, the one the tests keep equal to the installer's.
import re  # noqa: E402

from PyInstaller.utils.win32.versioninfo import (  # noqa: E402
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

APP_VERSION = re.search(r'^APP_VERSION = "([^"]+)"', (SERVER / "config" / "settings" / "base.py").read_text("utf-8"), re.M)[1]
numbers = tuple(int(n) for n in APP_VERSION.split(".")) + (0,) * (4 - len(APP_VERSION.split(".")))
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", "Sky Towers"),
                        StringStruct("FileDescription", "Sky Towers server (Windows service)"),
                        StringStruct("FileVersion", APP_VERSION),
                        StringStruct("InternalName", "skytowers-server"),
                        StringStruct("OriginalFilename", "skytowers-server.exe"),
                        StringStruct("ProductName", "Sky Towers"),
                        StringStruct("ProductVersion", APP_VERSION),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="skytowers-server",
    console=True,
    icon=str(SERVER.parent / "desktop" / "src-tauri" / "icons" / "icon.ico"),
    version=version_info,
)
coll = COLLECT(exe, a.binaries, a.datas, name="skytowers-server")
