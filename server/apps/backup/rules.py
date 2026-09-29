"""Backup naming, manifests, retention and import checks (spec §9). Pure functions, no ORM or I/O."""

import hashlib
import json
from datetime import datetime, timedelta

MANIFEST = "manifest.json"
DB_FILE = "hotel.db"


def file_name(hotel_id: str, seq: int, created_at: datetime) -> str:
    """``skytowers-<hotel8>-<seq:06d>-<YYYYMMDD-HHMM>.age`` (spec §9.1)."""
    return f"skytowers-{str(hotel_id).replace('-', '')[:8]}-{seq:06d}-{created_at:%Y%m%d-%H%M}.age"


def parse_file_name(name: str) -> tuple[str, int] | None:
    """(hotel8, seq) from a backup file name, or None for anything else."""
    if not (name.startswith("skytowers-") and name.endswith(".age")):
        return None
    parts = name[: -len(".age")].split("-")
    if len(parts) != 5 or not parts[2].isdigit():
        return None
    return parts[1], int(parts[2])


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_manifest(
    *,
    hotel_id,
    seq,
    created_at: datetime,
    schema_version,
    app_version,
    migrations,
    full,
    audit_seq,
    files: dict[str, bytes],
) -> dict:
    return {
        "hotel_id": str(hotel_id),
        "seq": seq,
        "created_at": created_at.isoformat(),
        "schema_version": schema_version,
        "app_version": app_version,
        "migrations": sorted(migrations),
        "full": full,
        "audit_seq": audit_seq,
        "files": [
            {"name": name, "size": len(data), "sha256": sha256_hex(data)} for name, data in sorted(files.items())
        ],
    }


def manifest_bytes(manifest: dict) -> bytes:
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8")


def mismatched_files(manifest: dict, files: dict[str, bytes]) -> list[str]:
    """Names whose content is missing or does not match the manifest's SHA-256 (the «التوقيع» check)."""
    bad = []
    for entry in manifest.get("files", []):
        data = files.get(entry["name"])
        if data is None or len(data) != entry["size"] or sha256_hex(data) != entry["sha256"]:
            bad.append(entry["name"])
    return bad


def to_delete(paths_newest_first: list[str], keep: int) -> list[str]:
    """Retention by count: keep the newest ``keep`` files."""
    return paths_newest_first[keep:] if keep > 0 else []


KEEP_NEWEST_BY_AGE = 3


def too_old(stamps_newest_first: list[tuple[str, datetime]], keep_days: int, now: datetime) -> list[str]:
    """Retention by age (spec §9.1.5): files older than ``keep_days``; 0 keeps everything. The newest three files
    are always kept, whatever their age: a PC left off for months keeps its copies, and a clock set far ahead (a
    wrong year) can no longer make every older backup «too old» at once (review 2026-09-29, E-8)."""
    if keep_days <= 0:
        return []
    limit = now - timedelta(days=keep_days)
    return [path for path, at in stamps_newest_first[KEEP_NEWEST_BY_AGE:] if at < limit]


def is_due(last_at: datetime | None, interval_hours: int, now: datetime) -> bool:
    return interval_hours > 0 and (last_at is None or now - last_at >= timedelta(hours=interval_hours))


def unknown_migrations(incoming: set[tuple[str, str]], known: set[tuple[str, str]]) -> set[tuple[str, str]]:
    """Migrations in the backup that this app does not have: the backup comes from a newer version."""
    return {m for m in incoming - known if m[0] in {k[0] for k in known}}


def check(key: str, label: str, detail: str, status: str) -> dict:
    """One of the five pre-merge checks shown in the import dialog (artboard 6.13 C)."""
    return {"key": key, "label": label, "detail": detail, "status": status}


def stale_hours(last_at: datetime | None, now: datetime, limit_hours: int) -> int | None:
    """Whole hours since the last backup once that reaches the limit (top bar red chip), else None.

    No backup at all is not «stale» here: the chip then says none was made yet.
    """
    if last_at is None or now - last_at < timedelta(hours=limit_hours):
        return None
    return int((now - last_at).total_seconds() // 3600)


# --- File format 2 (1.1): a small plain header before the age payload -------------------------------------------
# The header carries the key slots (the hotel key, each copy encrypted with an owner's or manager's password) so a
# backup opens on a new PC with that person's own username and password. Format 1 files are the bare age payload.
FORMAT2_MAGIC = b"SKYTOWERS-BACKUP-2\n"


def pack(header: dict, payload: bytes) -> bytes:
    """Magic line, one JSON line, then the age-encrypted payload."""
    line = json.dumps(header, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return FORMAT2_MAGIC + line + b"\n" + payload


def unpack(raw: bytes) -> tuple[dict | None, bytes]:
    """(header, payload) for a format 2 file; (None, raw) for a format 1 file or anything unreadable."""
    if not raw.startswith(FORMAT2_MAGIC):
        return None, raw
    rest = raw[len(FORMAT2_MAGIC) :]
    end = rest.find(b"\n")
    if end < 0:
        return None, raw
    try:
        header = json.loads(rest[:end].decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, raw
    return (header if isinstance(header, dict) else None), rest[end + 1 :]


def slot_for(header: dict | None, username: str) -> str | None:
    """The wrapped hotel key for this login name, if the file carries one (names compare case-insensitively)."""
    for slot in (header or {}).get("slots", []):
        if isinstance(slot, dict) and str(slot.get("username", "")).strip().lower() == username.strip().lower():
            return slot.get("wrapped")
    return None


def attachment_path(name: str) -> tuple[str, ...] | None:
    """The parts of an attachment's path inside ``attachments/`` from an archive entry name, or None when the entry
    is not an attachment or would leave that folder (``..``, an absolute path, a drive letter, a backslash)."""
    if not name.startswith("attachments/"):
        return None
    parts = tuple(name.removeprefix("attachments/").split("/"))
    if not parts or any(p in ("", ".", "..") or "\\" in p or ":" in p for p in parts):
        return None
    return parts


def key_id(public_key: str) -> str:
    """A short fingerprint of a public key for the backup header: tells a PC whether it holds the file's key without
    revealing the key (a file this PC should open but cannot is damaged; one for another key needs a login)."""
    return hashlib.sha256(public_key.strip().encode("ascii")).hexdigest()[:16]
