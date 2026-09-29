from datetime import datetime, time, timedelta

from django.conf import settings
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import HotelSettings

from . import services
from .models import Expense, ExpenseAttachment, Shift
from .serializers import (
    CloseShiftSerializer,
    CurrentShiftSerializer,
    ExpenseCreateSerializer,
    ExpenseReversalSerializer,
    ExpenseSerializer,
    ExpenseSummarySerializer,
    OpenShiftSerializer,
    ShiftDetailSerializer,
    ShiftHistorySerializer,
    ShiftSerializer,
    UploadSerializer,
)


def _detail(shift):
    return {"shift": shift, "totals": services.ShiftTotals.of(shift), "movements": services.movements(shift)}


def _local_day_start(day):
    return timezone.make_aware(datetime.combine(day, time.min))


class CurrentShiftView(APIView):
    """Shift card of artboard 6.7 A/B: the open shift with totals and movements, or the last closed one."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=CurrentShiftSerializer)
    def get(self, request):
        shift = services.current_shift()
        last = Shift.objects.filter(device=services.device(), closed_at__isnull=False).first()
        data = {
            "shift": shift,
            "totals": services.ShiftTotals.of(shift) if shift else None,
            "movements": services.movements(shift) if shift else [],
            "last_closed": last,
            "suggested_opening": last.opening if last else 0,
        }
        return Response(CurrentShiftSerializer(data).data)


class OpenShiftView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=OpenShiftSerializer, responses={201: ShiftSerializer})
    def post(self, request):
        data = OpenShiftSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        shift = services.open_shift(request.user, **data.validated_data)
        return Response(ShiftSerializer(shift).data, status=status.HTTP_201_CREATED)


class CloseShiftView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=CloseShiftSerializer, responses=ShiftSerializer)
    def post(self, request):
        data = CloseShiftSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(ShiftSerializer(services.close_shift(request.user, **data.validated_data)).data)


class ShiftHistoryView(APIView):
    """«سجل الورديات» (artboard 6.7 C) with the week's summary."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="shifts_list",
        parameters=[
            OpenApiParameter("date_from", str, description="YYYY-MM-DD; default 7 days ago"),
            OpenApiParameter("date_to", str, description="YYYY-MM-DD inclusive; default today"),
            OpenApiParameter("user", str, description="User id"),
        ],
        responses=ShiftHistorySerializer,
    )
    def get(self, request):
        today = timezone.localdate()
        params = request.query_params
        date_from = (
            datetime.fromisoformat(params["date_from"]).date() if "date_from" in params else today - timedelta(6)
        )
        date_to = datetime.fromisoformat(params["date_to"]).date() if "date_to" in params else today
        qs = Shift.objects.filter(
            closed_at__isnull=False,
            opened_at__gte=_local_day_start(date_from),
            opened_at__lt=_local_day_start(date_to + timedelta(days=1)),
        ).select_related("created_by", "closed_by")
        if user := params.get("user"):
            qs = qs.filter(Q(created_by_id=user) | Q(closed_by_id=user))
        shifts = []
        for shift in qs.order_by("-opened_at"):
            totals = services.ShiftTotals.of(shift)
            shift.receipts, shift.cash_expenses = totals.receipts["cash"], totals.expenses["cash"]
            shifts.append(shift)
        diffs = [s.difference for s in shifts if s.difference]
        data = {"count": len(shifts), "with_difference": len(diffs), "net_difference": sum(diffs), "shifts": shifts}
        return Response(ShiftHistorySerializer(data).data)


class ShiftDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ShiftDetailSerializer)
    def get(self, request, pk):
        return Response(ShiftDetailSerializer(_detail(get_object_or_404(Shift, pk=pk))).data)


# --- Expenses ---------------------------------------------------------------------------


def _expense_context():
    return {"threshold": HotelSettings.load().expense_attachment_threshold}


def _expenses():
    return Expense.objects.select_related("created_by", "room", "reversed_by").prefetch_related("attachments")


@extend_schema(
    parameters=[
        OpenApiParameter("scope", str, enum=["shift", "today", "month"], description="Default: month"),
        OpenApiParameter("category", str),
    ]
)
class ExpenseListView(ListAPIView):
    """Artboard 6.8: «هذه الوردية / اليوم / هذا الشهر» and a category filter."""

    permission_classes = [IsAuthenticated]
    serializer_class = ExpenseSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), **_expense_context()}

    def get_queryset(self):
        params = self.request.query_params
        qs = _expenses()
        scope = params.get("scope", "month")
        today = timezone.localdate()
        if scope == "shift":
            shift = services.current_shift()
            qs = qs.filter(shift=shift) if shift else qs.none()
        elif scope == "today":
            qs = qs.filter(spent_at__gte=_local_day_start(today))
        else:
            qs = qs.filter(spent_at__gte=_local_day_start(today.replace(day=1)))
        if category := params.get("category"):
            qs = qs.filter(category=category)
        return qs.order_by("-spent_at")

    @extend_schema(request=ExpenseCreateSerializer, responses={201: ExpenseSerializer})
    def post(self, request):
        data = ExpenseCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        expense = services.create_expense(request.user, **data.validated_data)
        return Response(
            ExpenseSerializer(_expenses().get(pk=expense.pk), context=_expense_context()).data,
            status=status.HTTP_201_CREATED,
        )


class ExpenseSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ExpenseSummarySerializer)
    def get(self, request):
        shift = services.current_shift()
        shift_qs = Expense.objects.filter(shift=shift) if shift else Expense.objects.none()
        month_qs = Expense.objects.filter(spent_at__gte=_local_day_start(timezone.localdate().replace(day=1)))
        by_cat = month_qs.values("category").annotate(s=Sum("amount")).order_by("-s").first()
        threshold = HotelSettings.load().expense_attachment_threshold
        awaiting = (
            Expense.objects.filter(amount__gt=threshold, reverses__isnull=True, reversed_by__isnull=True)
            .filter(attachments__isnull=True)
            .count()
        )
        data = {
            "shift_total": services.expenses_total(shift_qs),
            "shift_count": shift_qs.count(),
            "month_total": services.expenses_total(month_qs),
            "top_category": by_cat["category"] if by_cat else None,
            "top_category_total": by_cat["s"] if by_cat else 0,
            "awaiting_attachment": awaiting,
        }
        return Response(ExpenseSummarySerializer(data).data)


class ReverseExpenseView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ExpenseReversalSerializer, responses={201: ExpenseSerializer})
    def post(self, request, pk):
        from apps.accounts.services import verify_manager_override

        get_object_or_404(Expense, pk=pk)
        data = ExpenseReversalSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        reason, password = data.validated_data["reason"], data.validated_data["manager_password"]
        approver = verify_manager_override(password, reason) if password else None
        reversal = services.reverse_expense(request.user, pk, reason=reason, approver=approver)
        return Response(
            ExpenseSerializer(_expenses().get(pk=reversal.pk), context=_expense_context()).data,
            status=status.HTTP_201_CREATED,
        )


class ExpenseAttachmentView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    @extend_schema(request=UploadSerializer, responses={201: ExpenseSerializer})
    def post(self, request, pk):
        get_object_or_404(Expense, pk=pk)
        data = UploadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.add_expense_attachment(request.user, pk, data.validated_data["file"].read())
        return Response(
            ExpenseSerializer(_expenses().get(pk=pk), context=_expense_context()).data, status=status.HTTP_201_CREATED
        )


class ExpenseAttachmentFileView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={(200, "image/jpeg"): OpenApiResponse(OpenApiTypes.BINARY)})
    def get(self, request, pk, att_pk):
        attachment = get_object_or_404(ExpenseAttachment, pk=att_pk, expense_id=pk)
        data = (settings.RUNTIME.attachments_dir / attachment.file_path).read_bytes()
        return HttpResponse(data, content_type="image/jpeg")
