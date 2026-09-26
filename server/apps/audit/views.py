from datetime import date

from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsManager
from apps.core.errors import ApiError

from . import rules, services
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", default=None, read_only=True)
    category = serializers.SerializerMethodField()
    category_label = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "seq",
            "at",
            "actor",
            "actor_name",
            "action",
            "category",
            "category_label",
            "entity",
            "entity_id",
            "before",
            "after",
            "hash",
        ]

    @extend_schema_field(serializers.ChoiceField(choices=rules.CATEGORY_KEYS))
    def get_category(self, row) -> str:
        return rules.category(row.action, row.after)

    def get_category_label(self, row) -> str:
        return rules.CATEGORIES[self.get_category(row)]


class AuditVerifySerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    first_broken_seq = serializers.IntegerField(allow_null=True)
    rows = serializers.IntegerField()


@extend_schema(
    parameters=[
        OpenApiParameter("entity", str, description="e.g. user, room, stay"),
        OpenApiParameter("id", str, description="Entity id"),
        OpenApiParameter("q", str, description="User name, action, entity or exact id"),
        OpenApiParameter("date_from", str, description="YYYY-MM-DD"),
        OpenApiParameter("date_to", str, description="YYYY-MM-DD inclusive"),
        OpenApiParameter("category", str, enum=rules.CATEGORY_KEYS),
    ]
)
class AuditLogListView(ListAPIView):
    """Read-only audit trail, newest first (Settings → سجل التدقيق)."""

    permission_classes = [IsManager]
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        query = self.request.query_params
        category = query.get("category", "")
        if category and category not in rules.CATEGORIES:
            raise ApiError("validation_error", 400, detail="تصنيف غير معروف.")
        try:
            date_from = date.fromisoformat(query["date_from"]) if query.get("date_from") else None
            date_to = date.fromisoformat(query["date_to"]) if query.get("date_to") else None
        except ValueError:
            raise ApiError("validation_error", 400, detail="صيغة التاريخ غير صحيحة (YYYY-MM-DD).") from None
        qs = AuditLog.objects.all()
        if entity := query.get("entity"):
            qs = qs.filter(entity=entity)
        if entity_id := query.get("id"):
            qs = qs.filter(entity_id=entity_id)
        return services.search(qs, q=query.get("q", ""), date_from=date_from, date_to=date_to, category=category)


class AuditVerifyView(APIView):
    permission_classes = [IsManager]

    @extend_schema(responses=AuditVerifySerializer)
    def get(self, request):
        broken = services.verify_chain()
        data = {"ok": broken is None, "first_broken_seq": broken, "rows": AuditLog.objects.count()}
        return Response(AuditVerifySerializer(data).data)
