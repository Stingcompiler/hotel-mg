"""The owner's age key pair (spec §9.1: backups are encrypted to the owner's public key).

The identity (private key) lives only on the owner PC under ``SKYTOWERS_HOME/keys``; on Windows it is
wrapped with DPAPI so another Windows account cannot read it. The public key (``age1…``) is entered
in the reception's backup settings.
"""

import sys
from pathlib import Path

from django.conf import settings
from pyrage import x25519


def identity_path() -> Path:
    return settings.RUNTIME.home / "keys" / "owner.age-identity"


def protect(data: bytes) -> bytes:
    if sys.platform == "win32":  # pragma: no cover - Windows only
        import win32crypt

        return win32crypt.CryptProtectData(data, "SkyTowers owner key", None, None, None, 0)
    return data


def unprotect(data: bytes) -> bytes:
    if sys.platform == "win32":  # pragma: no cover - Windows only
        import win32crypt

        return win32crypt.CryptUnprotectData(data, None, None, None, 0)[1]
    return data


def generate(path: Path | None = None) -> str:
    """Create the owner identity once; return its public key. Refuses to overwrite an existing key."""
    path = path or identity_path()
    if path.exists():
        return str(load(path).to_public())
    identity = x25519.Identity.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(protect(str(identity).encode("ascii")))
    return str(identity.to_public())


def load(path: Path | None = None) -> x25519.Identity:
    path = path or identity_path()
    return x25519.Identity.from_str(unprotect(path.read_bytes()).decode("ascii"))


def recipient(public_key: str) -> x25519.Recipient:
    return x25519.Recipient.from_str(public_key.strip())
