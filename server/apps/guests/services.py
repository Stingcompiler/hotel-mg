from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from apps.audit import services as audit
from apps.core import imaging
from apps.core.concurrency import get_for_update
from apps.core.errors import ApiError

from . import rules
from .models import Companion, Guest, GuestDocument

GUEST_FIELDS = ["full_name", "phone", "nationality", "id_type", "id_number", "warning_note"]


def search(q: str):
    """Match by name (letter variants folded), phone digits or exact ID number."""
    q = (q or "").strip()
    qs = Guest.objects.all()
    if not q:
        return qs
    cond = Q(search_name__contains=rules.normalize_name(q))
    digits = rules.normalize_phone(q).lstrip("+")
    if len(digits) >= 4:
        # Local form "09…" matches the stored international "+2499…": drop the trunk 0.
        cond |= Q(phone__contains=digits[1:] if digits.startswith("0") else digits)
    cond |= Q(id_number=rules.to_ascii_digits(q))
    return qs.filter(cond)


def _apply(guest: Guest, fields: dict) -> None:
    for name, value in fields.items():
        if name == "phone":
            value = rules.normalize_phone(value)
        elif name == "id_number":
            value = rules.to_ascii_digits(value).strip()
        setattr(guest, name, value)
    guest.search_name = rules.normalize_name(guest.full_name)


def _replace_companions(guest: Guest, companions: list[dict], actor) -> None:
    for old in guest.companions.filter(removed=False):
        old.removed = True
        old.save(update_fields=["removed"])
    for row in companions:
        Companion.objects.create(guest=guest, created_by=actor, **row)


def _snapshot(guest: Guest) -> dict:
    data = audit.snapshot(guest, GUEST_FIELDS)
    data["companions"] = [{"name": c.name, "relation": c.relation} for c in guest.companions.filter(removed=False)]
    return data


@transaction.atomic
def create_guest(actor, *, companions=(), **fields) -> Guest:
    guest = Guest(created_by=actor)
    _apply(guest, fields)
    guest.save()
    _replace_companions(guest, list(companions), actor)
    audit.record(actor=actor, action="guest.create", entity="guest", entity_id=guest.pk, after=_snapshot(guest))
    return guest


@transaction.atomic
def update_guest(actor, guest_id, *, version: int, companions=None, **fields) -> Guest:
    guest = get_for_update(Guest.objects, guest_id, version)
    before = _snapshot(guest)
    _apply(guest, fields)
    guest.save()
    if companions is not None:
        _replace_companions(guest, list(companions), actor)
    audit.record(
        actor=actor, action="guest.update", entity="guest", entity_id=guest.pk, before=before, after=_snapshot(guest)
    )
    return guest


# --- ID documents -----------------------------------------------------------------


def document_path(document: GuestDocument) -> Path:
    return settings.RUNTIME.attachments_dir / document.file_path


@transaction.atomic
def add_document(actor, guest_id, raw: bytes) -> GuestDocument:
    guest = Guest.objects.get(pk=guest_id)
    try:
        stored = imaging.store_image(raw, f"guests/{guest.pk}")
    except imaging.InvalidImage:
        raise ApiError("invalid_image", 400) from None
    try:
        document = GuestDocument.objects.create(
            guest=guest, file_path=stored.relative_path, size=stored.size, sha256=stored.sha256, created_by=actor
        )
        audit.record(
            actor=actor,
            action="guest.add_document",
            entity="guest",
            entity_id=guest.pk,
            after={"document": str(document.pk), "size": document.size, "sha256": document.sha256},
        )
    except Exception:
        stored.absolute_path.unlink(missing_ok=True)  # no row, no file
        raise
    return document


@transaction.atomic
def open_document(actor, document_id) -> tuple[GuestDocument, bytes]:
    """Full, unblurred ID image — manager/owner only, and every view is audited («عرض حساس»)."""
    document = GuestDocument.objects.select_related("guest").get(pk=document_id)
    data = document_path(document).read_bytes()
    audit.record(
        actor=actor,
        action="guest.view_document",
        entity="guest",
        entity_id=document.guest_id,
        after={"document": str(document.pk)},
    )
    return document, data
