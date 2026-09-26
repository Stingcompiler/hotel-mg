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
import secrets
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

ROLES = ("reception", "owner")

# Stable hotel id for development machines without a config.json, so seeded
# data and imported backups keep matching across restarts.
DEV_HOTEL_ID = uuid.UUID("5a7e0000-0000-4000-8000-000000000001")


def default_home() -> Path:
    env = os.environ.get("SKYTOWERS_HOME")
    if env:
        return Path(env)
    if sys.platform == "win32":
        return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "SkyTowers"
    return Path(__file__).resolve().parent.parent / ".devdata"


@dataclass(frozen=True)
class RuntimeConfig:
    home: Path
    role: str
    hotel_id: uuid.UUID | None
    secret_key: str
    second_backup_dir: Path | None = None

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
    )
