from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsManager
from apps.accounts.services import require_confirmation

from .clock import approve_clock, is_clock_blocked
from .models import SCHEMA_VERSION


class SystemStatusSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["reception", "owner"])
    hotel_id = serializers.UUIDField(allow_null=True)
    last_backup = serializers.DateTimeField(allow_null=True)
    data_as_of = serializers.DateTimeField(allow_null=True)
    clock_blocked = serializers.BooleanField()
    version = serializers.CharField()
    schema_version = serializers.IntegerField()


class SystemStatusView(APIView):
    """Read before login: the SPA picks the reception or owner shell from ``role`` (spec §10.4)."""

    permission_classes = [AllowAny]

    @extend_schema(responses=SystemStatusSerializer)
    def get(self, request):
        data = {
            "role": settings.SKYTOWERS_ROLE,
            "hotel_id": settings.RUNTIME.hotel_id,
            "last_backup": None,  # B4: latest successful BackupRun
            "data_as_of": None,  # B4: owner PC, created_at of the last imported backup
            "clock_blocked": is_clock_blocked(),
            "version": settings.APP_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
        return Response(SystemStatusSerializer(data).data)


class ClockApproveView(APIView):
    """Manager accepts the device clock after a rollback block (spec §6.7). Needs X-Confirm-Token."""

    permission_classes = [IsManager]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        require_confirmation(request)
        approve_clock(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
