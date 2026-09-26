from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsManager

from . import services
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", default=None, read_only=True)

    class Meta:
        model = AuditLog
        fields = ["id", "seq", "at", "actor", "actor_name", "action", "entity", "entity_id", "before", "after", "hash"]


class AuditVerifySerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    first_broken_seq = serializers.IntegerField(allow_null=True)
    rows = serializers.IntegerField()


@extend_schema(
    parameters=[
        OpenApiParameter("entity", str, description="e.g. user, room, stay"),
        OpenApiParameter("id", str, description="Entity id"),
    ]
)
class AuditLogListView(ListAPIView):
    """Read-only audit trail, newest first (Settings → سجل التدقيق)."""

    permission_classes = [IsManager]
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        qs = AuditLog.objects.select_related("actor").order_by("-seq")
        if entity := self.request.query_params.get("entity"):
            qs = qs.filter(entity=entity)
        if entity_id := self.request.query_params.get("id"):
            qs = qs.filter(entity_id=entity_id)
        return qs


class AuditVerifyView(APIView):
    permission_classes = [IsManager]

    @extend_schema(responses=AuditVerifySerializer)
    def get(self, request):
        broken = services.verify_chain()
        data = {"ok": broken is None, "first_broken_seq": broken, "rows": AuditLog.objects.count()}
        return Response(AuditVerifySerializer(data).data)
