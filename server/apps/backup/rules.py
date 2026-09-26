"""Backup naming, manifests, retention and import checks (spec §9). Pure functions, no ORM or I/O."""

import hashlib
import json
from datetime import datetime, timedelta

MANIFEST = "manifest.json"
DB_FILE = "hotel.db"
FULL_EVERY = timedelta(days=7)


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


def needs_full(last_full_at: datetime | None, now: datetime) -> bool:
    """Weekly full backup (all attachments); in between, only attachments changed since the last full."""
    return last_full_at is None or now - last_full_at >= FULL_EVERY


def to_delete(paths_newest_first: list[str], keep: int) -> list[str]:
    """Retention by count: keep the newest ``keep`` files."""
    return paths_newest_first[keep:] if keep > 0 else []


def too_old(stamps_newest_first: list[tuple[str, datetime]], keep_days: int, now: datetime) -> list[str]:
    """Retention by age (spec §9.1.5): files older than ``keep_days``; 0 keeps everything. The newest file
    is always kept, whatever its age, so a PC left off for months still has one copy."""
    if keep_days <= 0:
        return []
    limit = now - timedelta(days=keep_days)
    return [path for path, at in stamps_newest_first[1:] if at < limit]


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
