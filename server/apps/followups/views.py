from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsManager
from apps.accounts.services import require_confirmation

from . import services
from .models import AlertRule, FollowupTask
from .serializers import (
    ActionSerializer,
    AlertRuleSerializer,
    AlertRuleUpdateSerializer,
    BoardSerializer,
    PreviewRequestSerializer,
    PreviewSerializer,
    TaskActionSerializer,
    TaskCountSerializer,
    TaskRowSerializer,
    ToastBatchSerializer,
)


class BoardView(APIView):
    """Follow-ups screen (artboard 6.6): متأخرة / اليوم / القادمة and system tasks. Poll every 30 s."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=BoardSerializer)
    def get(self, request):
        return Response(BoardSerializer(services.board()).data)


class TaskListView(APIView):
    """Spec §10.4: ``tasks?status=open`` (open, snoozed, waiting, neglected) and ``&count`` for badges."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str, enum=["open", "all"]),
            OpenApiParameter("count", bool, description="Deprecated: returns the TaskCount shape; use tasks/count."),
        ],
        responses=TaskRowSerializer(many=True),
    )
    def get(self, request):
        qs = FollowupTask.objects.select_related(
            "rule", "shift__created_by", "room", "stay__reservation__room", "stay__reservation__guest"
        )
        if request.query_params.get("status", "open") == "open":
            qs = qs.filter(status__in=OPEN_STATUSES)
        if "count" in request.query_params:
            return Response(_task_count())
        today = timezone.localdate()
        return Response(TaskRowSerializer([services.task_row(t, today) for t in qs.order_by("due_at")], many=True).data)


OPEN_STATUSES = ["open", "snoozed", "waiting", "neglected"]


def _task_count() -> dict:
    return {"count": FollowupTask.objects.filter(status__in=OPEN_STATUSES).count(), **services.summary_counts()}


class TaskCountView(APIView):
    """Badge numbers for the login screen, sidebar and top bar (spec §10.4 ``tasks?status=open&count``)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=TaskCountSerializer)
    def get(self, request):
        return Response(TaskCountSerializer(_task_count()).data)


class TaskDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="followups_task_history",
        responses=TaskActionSerializer(many=True),
        description="The task's action history.",
    )
    def get(self, request, pk):
        task = get_object_or_404(FollowupTask, pk=pk)
        return Response(TaskActionSerializer(task.actions.select_related("created_by"), many=True).data)


class TaskActionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ActionSerializer, responses=TaskRowSerializer)
    def post(self, request, pk):
        get_object_or_404(FollowupTask, pk=pk)
        data = ActionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        task = services.act(
            request.user,
            pk,
            v["action"],
            note=v["note"],
            until=v.get("until"),
            version=v.get("version"),
            stay_params=v.get("stay"),
        )
        task = FollowupTask.objects.select_related(
            "rule", "shift__created_by", "room", "stay__reservation__room", "stay__reservation__guest"
        ).get(pk=task.pk)
        return Response(TaskRowSerializer(services.task_row(task, timezone.localdate())).data)


class ToastsView(APIView):
    """Tray poll (every 30 s): notifications newer than ``after``."""

    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[OpenApiParameter("after", int)], responses=ToastBatchSerializer)
    def get(self, request):
        after = int(request.query_params.get("after", 0) or 0)
        toasts = services.toasts_after(after)
        return Response(ToastBatchSerializer({"cursor": toasts[-1].seq if toasts else after, "toasts": toasts}).data)


class RuleListView(APIView):
    def get_permissions(self):
        return [IsManager()] if self.request.method == "POST" else [IsAuthenticated()]

    @extend_schema(responses=AlertRuleSerializer(many=True))
    def get(self, request):
        return Response(AlertRuleSerializer(AlertRule.objects.all(), many=True).data)

    @extend_schema(request=AlertRuleSerializer, responses={201: AlertRuleSerializer})
    def post(self, request):
        data = AlertRuleSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(
            AlertRuleSerializer(services.create_rule(request.user, **data.validated_data)).data,
            status=status.HTTP_201_CREATED,
        )


class RuleDetailView(APIView):
    permission_classes = [IsManager]

    @extend_schema(request=AlertRuleUpdateSerializer, responses=AlertRuleSerializer)
    def patch(self, request, pk):
        rule = get_object_or_404(AlertRule, pk=pk)
        data = AlertRuleUpdateSerializer(rule, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        if data.validated_data.get("is_active") is False and rule.is_active:
            require_confirmation(request)  # disabling a rule is sensitive (spec §6.8)
        return Response(AlertRuleSerializer(services.update_rule(request.user, pk, **data.validated_data)).data)


class RulePreviewView(APIView):
    """Live preview while editing a rule (artboard 6.11: «معاينة — إقامة شهرية تنتهي …»)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=PreviewRequestSerializer, responses=PreviewSerializer)
    def post(self, request):
        data = PreviewRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        last_night = values.pop("last_night")
        return Response(PreviewSerializer(services.preview(values, last_night)).data)
