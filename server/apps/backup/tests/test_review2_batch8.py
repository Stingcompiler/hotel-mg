"""Review 2026-09-29, batch 8: backups and uploads (C-9, C-11, C-13, C-14, C-15, C-17)."""

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.services import login_with_password
from apps.backup import merge
from apps.core import imaging
from apps.core.errors import ApiError
from conftest import PASSWORD

pytestmark = pytest.mark.django_db


def test_a_stored_path_cannot_leave_the_attachments_folder(settings):
    """C-11: a database from a backup must not make the server read files outside the attachments folder."""
    inside = imaging.stored_path("guests/2026/09/photo.jpg")
    assert inside.is_relative_to(settings.RUNTIME.attachments_dir.resolve())
    with pytest.raises(ApiError):
        imaging.stored_path("../../config.json")


def test_uploads_are_refused_before_they_are_read():
    """C-17."""
    imaging.check_upload_size(imaging.MAX_UPLOAD_BYTES)
    with pytest.raises(ApiError):
        imaging.check_upload_size(imaging.MAX_UPLOAD_BYTES + 1)


def test_an_import_replaces_an_attachment_cut_short_by_a_power_cut(settings):
    """C-13: a truncated file used to stay forever (existing files were skipped)."""
    root = settings.RUNTIME.attachments_dir
    dest = root / "guests" / "cut.jpg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"half")
    copied = merge._copy_attachments({"attachments/guests/cut.jpg": b"the whole file", "attachments/../evil": b"x"})
    assert copied == 1 and dest.read_bytes() == b"the whole file"
    assert not (dest.parent / "cut.jpg.part").exists()
    assert merge._copy_attachments({"attachments/guests/cut.jpg": b"the whole file"}) == 0  # already complete


def test_the_owner_pc_can_approve_its_own_clock():
    """C-14: the read-only middleware refused the approval, so imports stayed blocked after a clock rollback."""
    with override_settings(SKYTOWERS_ROLE="owner"):
        res = APIClient().post("/api/v1/system/clock/approve", {}, format="json")
    assert res.json().get("code") != "owner_read_only"


def test_only_the_owner_changes_who_receives_the_backups(manager_api, make_user, confirm):
    """C-15: a manager could add a key that keeps receiving every backup."""
    settings_url = "/api/v1/backup/settings"
    current = manager_api.get(settings_url).json()
    same = {"version": current["version"], "keep_count": 12, "owner_recipient": current["owner_recipient"]}
    res = manager_api.patch(settings_url, same, format="json")
    assert res.status_code == 200, res.json()  # unchanged recipients: nothing sensitive
    change = {"version": res.json()["version"], "second_dir": "D:\\\\copies"}
    res = manager_api.patch(settings_url, change, format="json")
    assert res.status_code == 403 and res.json()["code"] == "permission_denied"
    owner = make_user("owner", role="owner", full_name="المالك")
    owner_api = APIClient()
    owner_api.credentials(HTTP_AUTHORIZATION=f"Token {login_with_password(owner.username, PASSWORD).token}")
    res = owner_api.patch(settings_url, change, format="json")
    assert res.status_code == 403 and res.json()["code"] == "confirmation_required"
    confirm(owner_api)
    assert owner_api.patch(settings_url, change, format="json").status_code == 200


def test_the_owner_pc_import_is_refused_on_the_reception_pc(manager_api):
    """C-9: a manager at the reception PC could merge a crafted file into the live data."""
    res = manager_api.post("/api/v1/owner/backup/run")
    assert res.status_code == 403
