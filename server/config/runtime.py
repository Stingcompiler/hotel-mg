"""Per-PC runtime configuration.

Everything that differs between the reception PC and the owner PC lives in
``<SKYTOWERS_HOME>/config.json``. The installer writes that file; in
development it is optional and sensible defaults are used.

Layout under SKYTOWERS_HOME (spec §2)::

    config.json            {role, hotel_id, secret_key, ...}
    data/hotel.db          SQLite (WAL)
    data/attachments/
    backups/
"""

from __future__ import annotations

import json
import os
import platform
import secrets
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

ROLES = ("reception", "owner")

# Stable hotel id for development machines without a config.json, so seeded
# data and imported backups keep matching across restarts.
DEV_HOTEL_ID = uuid.UUID("5a7e0000-0000-4000-8000-000000000001")


def installed_home() -> Path | None:
    """The installed program's data folder (%ProgramData%\\SkyTowers); None off Windows."""
    if sys.platform != "win32":
        return None
    return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "SkyTowers"


def default_home() -> Path:
    """SKYTOWERS_HOME, else the installed folder for the installed program (the PyInstaller bundle), else
    ``server/.devdata``. A source checkout on a Windows PC never defaults to the installed folder: a
    ``seed_demo`` run from the checkout once filled a freshly installed app with the demo hotel."""
    env = os.environ.get("SKYTOWERS_HOME")
    if env:
        return Path(env)
    installed = installed_home()
    if installed is not None and getattr(sys, "frozen", False):
        return installed
    return Path(__file__).resolve().parent.parent / ".devdata"


def is_installed_home(home: Path) -> bool:
    installed = installed_home()
    return installed is not None and os.path.normcase(os.path.abspath(home)) == os.path.normcase(
        os.path.abspath(installed)
    )


@dataclass(frozen=True)
class RuntimeConfig:
    home: Path
    role: str
    hotel_id: uuid.UUID | None
    secret_key: str
    second_backup_dir: Path | None = None
    device_name: str = "RECEPTION-PC"

    @property
    def data_dir(self) -> Path:
        return self.home / "data"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "hotel.db"

    @property
    def attachments_dir(self) -> Path:
        return self.data_dir / "attachments"

    @property
    def backups_dir(self) -> Path:
        return self.home / "backups"


def _secret_key(home: Path, raw: dict) -> str:
    if raw.get("secret_key"):
        return raw["secret_key"]
    key_file = home / "secret.key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = secrets.token_urlsafe(50)
    home.mkdir(parents=True, exist_ok=True)
    key_file.write_text(key, encoding="utf-8")
    return key


def load(home: Path | None = None, role_override: str | None = None) -> RuntimeConfig:
    home = home or default_home()
    config_file = home / "config.json"
    raw: dict = {}
    if config_file.exists():
        raw = json.loads(config_file.read_text(encoding="utf-8"))

    role = role_override or raw.get("role", "reception")
    if role not in ROLES:
        raise ValueError(f"config.json: role must be one of {ROLES}, got {role!r}")

    if "hotel_id" in raw:
        # The owner PC starts with an empty hotel_id until the first import.
        hotel_id = uuid.UUID(raw["hotel_id"]) if raw["hotel_id"] else None
    else:
        hotel_id = DEV_HOTEL_ID

    second = raw.get("second_backup_dir")
    return RuntimeConfig(
        home=home,
        role=role,
        hotel_id=hotel_id,
        secret_key=_secret_key(home, raw),
        second_backup_dir=Path(second) if second else None,
        # One open cash shift per device (spec §6.5); defaults to the Windows computer name.
        device_name=raw.get("device_name") or platform.node() or "PC",
    )


def init_config(home: Path, role: str, force: bool = False) -> bool:
    """Installer step: write ``config.json`` once (spec §11). Upgrades keep the existing file.

    Reception gets a new hotel id; the owner PC leaves it empty until the first import adopts the hotel's.
    ``force`` rewrites the role of an existing install (the installer's question answered wrongly): the other
    keys stay, and a reception PC takes the hotel id its database already carries rather than a fresh one.
    Returns True when the file was written.
    """
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}, got {role!r}")
    config_file = home / "config.json"
    if config_file.exists() and not force:
        return False
    home.mkdir(parents=True, exist_ok=True)
    raw = json.loads(config_file.read_text(encoding="utf-8")) if config_file.exists() else {}
    raw["role"] = role
    if role == "reception":
        raw["hotel_id"] = raw.get("hotel_id") or str(hotel_in_database(home / "data" / "hotel.db") or uuid.uuid4())
    else:
        raw["hotel_id"] = raw.get("hotel_id") or ""
    config_file.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    return True


def hotel_in_database(db_path: Path) -> uuid.UUID | None:
    """The hotel the database belongs to (its first user's row), without Django — for ``init --force``."""
    import sqlite3

    if not db_path.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = con.execute("select hotel_id from accounts_user order by created_at limit 1").fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    return uuid.UUID(str(row[0])) if row and row[0] else None
