"""Apply a hotel adopted from a backup on a new PC (1.1), at service start, before Django opens the database.

``apps.backup.adopt.prepare`` checks the file and leaves ``<home>/pending-import/`` with ``plan.json`` and the data,
then the service restarts. Here the empty install's files move to ``backups/pre-import-<stamp>/`` (nothing is
deleted) and ``config.json`` takes the chosen role:

- ``work``: this PC replaces a reception PC — the backup's database and attachments become this PC's, role reception;
- ``view``: the owner's PC — role owner with an empty database; ``adopt.finish_pending`` merges the backup after the
  migrations, as the first import of an owner PC.

Every step is recorded in ``plan.json`` (written through a temporary file) and repeats safely: a power cut at any
point is finished by the next start instead of leaving a service that cannot start.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

PENDING_DIR = "pending-import"
PLAN = "plan.json"
DB_FILES = ("hotel.db", "hotel.db-wal", "hotel.db-shm")


def pending_dir(home: Path) -> Path:
    return home / PENDING_DIR


def read_plan(home: Path) -> dict | None:
    path = pending_dir(home) / PLAN
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, data: dict) -> None:
    """Replace a small JSON file atomically: readers see the old or the new content, never half of it."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _move(src: Path, dst: Path) -> None:
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))


def apply(home: Path, now: datetime | None = None) -> str | None:
    """Swap the files and set the role. Returns the mode applied, or None when nothing was pending."""
    plan = read_plan(home)
    if plan is None or plan.get("applied"):
        return None
    pending, data = pending_dir(home), home / "data"
    plan_file = pending / PLAN

    if not plan.get("kept"):
        plan["kept"] = str(home / "backups" / f"pre-import-{(now or datetime.now()):%Y%m%d-%H%M%S}")
        write_json(plan_file, plan)
    keep = Path(plan["kept"])

    if not plan.get("moved_old"):  # the empty install goes aside (a repeat finds nothing left to move)
        for name in DB_FILES:
            _move(data / name, keep / name)
        _move(data / "attachments", keep / "attachments")
        plan["moved_old"] = True
        write_json(plan_file, plan)

    data.mkdir(parents=True, exist_ok=True)
    if plan["mode"] == "work" and not plan.get("placed"):
        _move(pending / "hotel.db", data / "hotel.db")
        _move(pending / "attachments", data / "attachments")
        plan["placed"] = True
        write_json(plan_file, plan)

    config_file = home / "config.json"
    config = json.loads(config_file.read_text(encoding="utf-8")) if config_file.exists() else {}
    if plan["mode"] == "work":
        config["role"], config["hotel_id"] = "reception", plan["hotel_id"]
    else:
        config["role"], config["hotel_id"] = "owner", ""  # the first import adopts the hotel id
    write_json(config_file, config)

    plan["applied"] = True
    write_json(plan_file, plan)
    return plan["mode"]
