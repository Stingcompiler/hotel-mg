"""The server's APP_VERSION and the installer's version move together (1.1.4 shipped a server saying 1.1.3)."""

import json
import re
from pathlib import Path

from django.conf import settings

ROOT = Path(__file__).resolve().parents[2]


def test_server_and_desktop_versions_agree():
    tauri = json.loads((ROOT / "desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))["version"]
    package = json.loads((ROOT / "desktop/package.json").read_text(encoding="utf-8"))["version"]
    cargo_toml = (ROOT / "desktop/src-tauri/Cargo.toml").read_text(encoding="utf-8")
    cargo = re.search(r'^version = "([^"]+)"', cargo_toml, re.M)
    assert settings.APP_VERSION == tauri == package == cargo.group(1)


def test_every_version_number_is_the_right_one():
    """F-22: the Python package said 0.1.0 and the OpenAPI document 1.0.0."""
    pyproject = (ROOT / "server/pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1) == settings.APP_VERSION
    contract = (ROOT / "api/VERSION").read_text(encoding="utf-8").strip()
    assert settings.SPECTACULAR_SETTINGS["VERSION"] == contract
