"""Backup keys (age / X25519) kept under ``SKYTOWERS_HOME/keys``.

- The **hotel key** (1.1, ``hotel.age-identity``): made by the reception PC; every backup is encrypted to it. Its
  identity also travels inside each backup wrapped with the owner's and managers' passwords (keyslots.py); a PC
  that opens a file with one of those logins keeps it here for later imports.
- A pre-1.1 **owner key** (``owner.age-identity``): kept so owner PCs installed before 1.1 still open backups.

On Windows the files are wrapped with DPAPI in the **machine** scope: any process of this PC can unwrap them — the
service (SYSTEM) and the installer's commands (an administrator) alike — and no other PC can; the installer limits
the keys folder to Administrators and SYSTEM. 1.1.0–1.1.1 used the user scope, so only the service could read the
key and the installer's pre-upgrade backup failed; ``migrate_protection`` rewraps those files at service start.
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from django.conf import settings
from pyrage import x25519

log = logging.getLogger(__name__)
_MACHINE_SCOPE = 0x4  # CRYPTPROTECT_LOCAL_MACHINE


def identity_path() -> Path:
    return settings.RUNTIME.home / "keys" / "owner.age-identity"


def protect(data: bytes) -> bytes:
    if sys.platform == "win32":  # pragma: no cover - Windows only
        import win32crypt

        return win32crypt.CryptProtectData(data, "SkyTowers key", None, None, None, _MACHINE_SCOPE)
    return data


def unprotect(data: bytes) -> bytes:
    if sys.platform == "win32":  # pragma: no cover - Windows only
        import win32crypt

        return win32crypt.CryptUnprotectData(data, None, None, None, 0)[1]
    return data


def _write(path: Path, identity: str) -> None:
    """Write through a temporary file: a power cut never leaves half a key."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(protect(identity.encode("ascii")))
    os.replace(tmp, path)


def generate(path: Path | None = None) -> str:
    """Create the identity once; return its public key. Refuses to overwrite an existing key."""
    path = path or identity_path()
    if path.exists():
        return str(load(path).to_public())
    identity = x25519.Identity.generate()
    _write(path, str(identity))
    return str(identity.to_public())


def load(path: Path | None = None) -> x25519.Identity:
    path = path or identity_path()
    return x25519.Identity.from_str(unprotect(path.read_bytes()).decode("ascii"))


def _readable(path: Path) -> x25519.Identity | None:
    """The key in this file, or None — a file this process cannot unwrap is moved aside, never fatal."""
    if not path.exists():
        return None
    try:
        return load(path)
    except Exception:  # noqa: BLE001 - DPAPI of another account/PC, a damaged file
        aside = path.with_name(f"{path.name}.unreadable-{datetime.now():%Y%m%d-%H%M%S}")
        log.exception("backup key %s cannot be read here; moved to %s", path, aside.name)
        try:
            path.replace(aside)
        except OSError:
            log.exception("could not move %s aside", path)
        return None


def recipient(public_key: str) -> x25519.Recipient:
    return x25519.Recipient.from_str(public_key.strip())


def hotel_identity_path() -> Path:
    return settings.RUNTIME.home / "keys" / "hotel.age-identity"


def ensure_hotel_key() -> str:
    """The hotel's public key, creating the key pair on first use. Reception PC only (the service calls it)."""
    return generate(hotel_identity_path())


def hotel_identity() -> x25519.Identity | None:
    return _readable(hotel_identity_path())


def hotel_public_key() -> str | None:
    identity = hotel_identity()
    return str(identity.to_public()) if identity else None


def save_hotel_identity(identity: str) -> None:
    """Adopt a hotel's key (an import opened with a login). A different key already here is kept beside it."""
    path = hotel_identity_path()
    current = _readable(path)
    if current is not None:
        if str(current) == identity:
            return
        path.replace(path.with_name(path.name + ".previous"))
    _write(path, identity)


def local_identities() -> list[x25519.Identity]:
    """Every key this PC holds that may open a backup: the hotel key, then a pre-1.1 owner key."""
    return [i for i in (hotel_identity(), _readable(identity_path())) if i is not None]


def migrate_protection() -> int:
    """Service start (SYSTEM): rewrap the key files in the machine scope. Returns how many were rewritten."""
    if sys.platform != "win32":
        return 0
    done = 0
    for path in (hotel_identity_path(), identity_path()):  # pragma: no cover - Windows only
        if not path.exists():
            continue
        raw = path.read_bytes()
        try:
            import win32crypt

            description = win32crypt.CryptUnprotectData(raw, None, None, None, 0)[0]
            identity = win32crypt.CryptUnprotectData(raw, None, None, None, 0)[1].decode("ascii")
        except Exception:  # noqa: BLE001 - left for _readable to move aside when used
            continue
        if description == "SkyTowers key":
            continue  # already machine scope (written by this build)
        _write(path, identity)
        done += 1
    return done
