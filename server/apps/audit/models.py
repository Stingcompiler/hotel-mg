from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from apps.core.models import AppendOnlyModel


class AuditLog(AppendOnlyModel):
    """Hash-chained, append-only record of every service action (spec §6.9).

    ``seq`` orders the chain per hotel; ``hash = sha256(prev_hash + canonical_json(row))``.
    The unique (hotel_id, seq) constraint makes a concurrent writer fail instead of forking the chain.
    """

    seq = models.PositiveBigIntegerField()
    actor = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    action = models.CharField(max_length=64)
    entity = models.CharField(max_length=64)
    entity_id = models.CharField(max_length=64, blank=True)
    before = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    after = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    at = models.DateTimeField()
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64)

    class Meta:
        ordering = ["seq"]
        constraints = [models.UniqueConstraint(fields=["hotel_id", "seq"], name="audit_seq_per_hotel")]
        indexes = [models.Index(fields=["entity", "entity_id"]), models.Index(fields=["at"])]

    def __str__(self):
        return f"#{self.seq} {self.action} {self.entity}:{self.entity_id}"
