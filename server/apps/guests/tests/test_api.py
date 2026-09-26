import io
import os

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.audit.models import AuditLog
from apps.guests import rules
from apps.guests.models import Companion, Guest, GuestDocument

pytestmark = pytest.mark.django_db

GUEST = {
    "full_name": "محمد عثمان الطيب",
    "phone": "+249 91 234 5678",
    "nationality": "سوداني",
    "id_type": "national_id",
    "id_number": "211-8842-1023-7",
    "companions": [{"name": "آمنة عثمان محمد", "relation": "زوجة"}],
}


@pytest.fixture
def guest(reception_api):
    res = reception_api.post("/api/v1/guests/", GUEST, format="json")
    assert res.status_code == 201, res.json()
    return Guest.objects.get(pk=res.json()["id"])


def _image(size=(1600, 1200), fmt="PNG") -> bytes:
    img = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3))  # noise: hard to compress
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


def test_create_normalizes_and_audits(guest, reception):
    assert guest.phone == "+249912345678"
    assert guest.search_name == "محمد عثمان الطيب"
    assert [c.name for c in guest.companions.all()] == ["آمنة عثمان محمد"]
    row = AuditLog.objects.get(action="guest.create")
    assert row.actor == reception and row.after["companions"] == [{"name": "آمنة عثمان محمد", "relation": "زوجة"}]


def test_validation_messages(reception_api):
    res = reception_api.post("/api/v1/guests/", {"full_name": "محمد", "phone": "12"}, format="json")
    assert res.status_code == 400
    assert set(res.json()["errors"]) == {"full_name", "phone"}


def test_id_number_is_masked_for_reception(reception_api, manager_api, guest):
    assert reception_api.get(f"/api/v1/guests/{guest.pk}").json()["id_number"] == "••••23-7"
    assert manager_api.get(f"/api/v1/guests/{guest.pk}").json()["id_number"] == "211-8842-1023-7"


@pytest.mark.parametrize("q", ["احمد", "أحمد", "محمد عثمان", "0912345678", "249912345678", "211-8842-1023-7"])
def test_search(reception_api, guest, q):
    reception_api.post("/api/v1/guests/", {"full_name": "أحمد علي النور"}, format="json")
    names = {g["full_name"] for g in reception_api.get("/api/v1/guests/", {"q": q}).json()["results"]}
    expected = {"أحمد علي النور"} if "حمد" in q and "محمد" not in q else {"محمد عثمان الطيب"}
    assert names == expected


def test_warning_filter(reception_api, guest):
    reception_api.post("/api/v1/guests/", {"full_name": "خالد إبراهيم", "warning_note": "دين سابق 8,000 ج.س"},
                       format="json")  # fmt: skip
    res = reception_api.get("/api/v1/guests/", {"warning": "1"}).json()["results"]
    assert [g["full_name"] for g in res] == ["خالد إبراهيم"]


def test_update_replaces_companions_without_deleting(reception_api, guest):
    res = reception_api.patch(
        f"/api/v1/guests/{guest.pk}",
        {"version": guest.version, "companions": [{"name": "علي محمد", "relation": "ابن"}]},
        format="json",
    )
    assert res.status_code == 200
    assert res.json()["companions"] == [{"name": "علي محمد", "relation": "ابن"}]
    assert Companion.objects.filter(guest=guest).count() == 2  # old one kept, flagged removed
    stale = reception_api.patch(f"/api/v1/guests/{guest.pk}", {"version": 1, "warning_note": "x"}, format="json")
    assert stale.status_code == 409


class TestDocuments:
    def upload(self, client, guest, raw, name="id.png"):
        return client.post(
            f"/api/v1/guests/{guest.pk}/documents", {"file": SimpleUploadedFile(name, raw)}, format="multipart"
        )

    def test_upload_is_compressed_under_limit(self, reception_api, guest):
        raw = _image()
        assert len(raw) > rules.MAX_DOCUMENT_BYTES
        res = self.upload(reception_api, guest, raw)
        assert res.status_code == 201, res.json()
        doc = GuestDocument.objects.get(pk=res.json()["id"])
        stored = settings.RUNTIME.attachments_dir / doc.file_path
        assert stored.exists()
        assert doc.size == stored.stat().st_size <= rules.MAX_DOCUMENT_BYTES
        with Image.open(stored) as img:
            assert img.format == "JPEG"

    def test_rejects_non_images(self, reception_api, guest):
        res = self.upload(reception_api, guest, b"%PDF-1.4 not an image", name="id.pdf")
        assert res.status_code == 400
        assert res.json()["code"] == "invalid_image"
        assert not GuestDocument.objects.exists()

    def test_viewing_is_manager_only_and_audited(self, reception_api, manager_api, guest, manager):
        doc_id = self.upload(reception_api, guest, _image((400, 300), "JPEG")).json()["id"]
        url = f"/api/v1/guests/{guest.pk}/documents/{doc_id}"
        assert reception_api.get(url).status_code == 403
        res = manager_api.get(url)
        assert res.status_code == 200
        assert res["Content-Type"] == "image/jpeg"
        assert res["Cache-Control"] == "no-store"
        assert AuditLog.objects.filter(action="guest.view_document", actor=manager).count() == 1

    def test_guest_detail_lists_documents(self, reception_api, guest):
        self.upload(reception_api, guest, _image((400, 300), "JPEG"))
        docs = reception_api.get(f"/api/v1/guests/{guest.pk}").json()["documents"]
        assert len(docs) == 1 and docs[0]["added_by"] == "أحمد علي"
