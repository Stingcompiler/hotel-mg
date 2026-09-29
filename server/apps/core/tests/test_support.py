"""«حزمة الدعم»: logs and versions on a USB stick, never secrets or hotel data."""

import io
import json
import zipfile

import pytest

from apps.backup import usb

pytestmark = pytest.mark.django_db


def test_the_support_bundle_goes_to_the_stick_without_secrets(
    manager_api, reception_api, settings, tmp_path, monkeypatch
):
    logs = tmp_path / "home" / "logs"
    logs.mkdir(parents=True)
    (logs / "server.log").write_text("2026-09-29 ERROR something broke\n", encoding="utf-8")
    monkeypatch.setattr(
        settings, "RUNTIME", __import__("dataclasses").replace(settings.RUNTIME, home=tmp_path / "home")
    )
    stick = tmp_path / "stick"
    stick.mkdir()
    monkeypatch.setattr(usb, "removable_drives", lambda: [{"drive": str(stick), "label": "", "free": 10**9}])

    assert reception_api.post("/api/v1/system/support-bundle", {"drive": str(stick)}, format="json").status_code == 403
    res = manager_api.post("/api/v1/system/support-bundle", {"drive": str(stick)}, format="json")
    assert res.status_code == 200, res.json()
    written = next((stick / "SkyTowers").glob("support-*.zip"))
    assert res.json()["path"] == str(written)
    with zipfile.ZipFile(io.BytesIO(written.read_bytes())) as zf:
        names = set(zf.namelist())
        assert {"info.json", "runs.json", "logs/server.log"} <= names
        info = json.loads(zf.read("info.json"))
        assert info["app_version"] == settings.APP_VERSION and "stays.0001_initial" in info["migrations"]
        everything = b"".join(zf.read(n) for n in names)
    assert settings.SECRET_KEY.encode() not in everything and not any(
        n.endswith((".db", ".age", "identity")) for n in names
    )
    res = manager_api.post("/api/v1/system/support-bundle", {"drive": "Q:\\"}, format="json")
    assert res.status_code == 400
