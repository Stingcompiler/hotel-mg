import json
from datetime import UTC

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.forms.models import model_to_dict
from django.utils import timezone

from apps.core.hotel import current_hotel_id

from . import rules
from .models import AuditLog

# Never copied into audit rows.
SECRET_FIELDS = frozenset({"password", "pin_hash"})


def snapshot(instance, fields=None) -> dict:
    """JSON-safe dict of a model instance for ``before``/``after``; secrets are dropped."""
    data = model_to_dict(instance, fields=fields)
    data["id"] = instance.pk
    for name in SECRET_FIELDS:
        data.pop(name, None)
    for name in ("version", "updated_at"):
        if hasattr(instance, name) and (fields is None or name in fields):
            data[name] = getattr(instance, name)
    return _json_roundtrip(data)


def _json_roundtrip(value):
    # Store exactly what the hash covers: what comes back from the JSON column.
    return None if value is None else json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def record(*, actor, action: str, entity: str, entity_id="", before=None, after=None) -> AuditLog | None:
    """Append one row to this hotel's chain. Call inside the service's transaction.

    The chain is written on the reception PC only; the owner PC receives it by import and must not fork it.
    """
    if settings.SKYTOWERS_ROLE == "owner":
        return None
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("audit.record() must run inside the service transaction")
    hotel_id = current_hotel_id()
    last = AuditLog.objects.filter(hotel_id=hotel_id).order_by("-seq").only("seq", "hash").first()
    seq = last.seq + 1 if last else 1
    prev_hash = last.hash if last else rules.GENESIS_HASH
    at = timezone.now().astimezone(UTC)
    before, after = _json_roundtrip(before), _json_roundtrip(after)
    payload = rules.row_payload(
        seq=seq,
        hotel_id=hotel_id,
        actor_id=actor.pk if actor else None,
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        before=before,
        after=after,
        at=at,
    )
    return AuditLog.objects.create(
        hotel_id=hotel_id,
        seq=seq,
        actor=actor,
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        before=before,
        after=after,
        at=at,
        prev_hash=prev_hash,
        hash=rules.chain_hash(prev_hash, payload),
        created_by=actor,
    )


def verify_chain(hotel_id=None, using: str = "default") -> int | None:
    """Return the seq of the first broken row of the hotel's chain, or None when intact."""
    hotel_id = hotel_id or current_hotel_id()
    rows = (
        {
            "seq": r.seq,
            "hotel_id": str(r.hotel_id),
            "actor_id": str(r.actor_id) if r.actor_id else None,
            "action": r.action,
            "entity": r.entity,
            "entity_id": r.entity_id,
            "before": r.before,
            "after": r.after,
            "at": r.at.astimezone(UTC),
            "prev_hash": r.prev_hash,
            "hash": r.hash,
        }
        for r in AuditLog.objects.using(using).filter(hotel_id=hotel_id).order_by("seq").iterator()
    )
    return rules.first_broken(rows)
