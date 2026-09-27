"""Apply a hotel adopted from a backup on a new PC (1.1), at service start, before Django opens the database.

``apps.backup.adopt.prepare`` checks the file and leaves ``<home>/pending-import/`` with ``plan.json`` and the data,
then the service restarts. Here the empty install's files move to ``backups/pre-import-<stamp>/`` (nothing is
deleted) and ``config.json`` takes the chosen role:

- ``work``: this PC replaces a reception PC — the backup's database and attachments become this PC's, role reception;
- ``view``: the owner's PC — role owner with an empty database; ``adopt.finish_pending`` merges the backup after the
  migrations, as the first import of an owner PC.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

PENDING_DIR = "pending-import"
PLAN = "plan.json"


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


def apply(home: Path, now: datetime | None = None) -> str | None:
    """Swap the files and set the role. Returns the mode applied, or None when nothing was pending."""
    plan = read_plan(home)
    if plan is None or plan.get("applied"):
        return None
    pending = pending_dir(home)
    data = home / "data"
    keep = home / "backups" / f"pre-import-{(now or datetime.now()):%Y%m%d-%H%M%S}"
    keep.mkdir(parents=True, exist_ok=True)
    for name in ("hotel.db", "hotel.db-wal", "hotel.db-shm"):
        if (data / name).exists():
            shutil.move(str(data / name), str(keep / name))
    if (data / "attachments").exists():
        shutil.move(str(data / "attachments"), str(keep / "attachments"))
    data.mkdir(parents=True, exist_ok=True)

    config_file = home / "config.json"
    config = json.loads(config_file.read_text(encoding="utf-8")) if config_file.exists() else {}
    if plan["mode"] == "work":
        shutil.move(str(pending / "hotel.db"), str(data / "hotel.db"))
        if (pending / "attachments").exists():
            shutil.move(str(pending / "attachments"), str(data / "attachments"))
        config["role"], config["hotel_id"] = "reception", plan["hotel_id"]
    else:
        config["role"], config["hotel_id"] = "owner", ""  # the first import adopts the hotel id
    config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    plan["applied"] = True
    plan["kept"] = str(keep)
    (pending / PLAN).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return plan["mode"]
