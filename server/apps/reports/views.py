from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rules as account_rules
from apps.accounts.permissions import IsManager
from apps.audit import rules as audit_rules
from apps.billing.models import Folio, Payment
from apps.cash.models import Expense, Shift
from apps.core.errors import ApiError
from apps.core.models import HotelSettings

from . import documents, exporters, queries  # noqa: F401  (queries registers the reports)
from .dashboard import owner_dashboard
from .dashboard_serializers import OwnerDashboardSerializer
from .document_serializers import (
    ExpenseReceiptDocumentSerializer,
    InvoiceDocumentSerializer,
    PaymentReceiptDocumentSerializer,
    ShiftStatementDocumentSerializer,
)
from .framework import REGISTRY, build


class ReportIndexItemSerializer(serializers.Serializer):
    name = serializers.CharField()
    title = serializers.CharField()
    badge = serializers.IntegerField(allow_null=True, help_text="Items needing attention (red count in the index).")


class ReportColumnSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    type = serializers.ChoiceField(choices=["text", "money", "int", "percent", "date", "datetime"])


class ReportSerializer(serializers.Serializer):
    name = serializers.CharField()
    columns = ReportColumnSerializer(many=True)
    rows = serializers.ListField(child=serializers.DictField())
    meta = serializers.DictField(help_text="title, as_of, date_from, date_to, formula, note, tiles, totals, filters")


REPORT_PARAMS = [
    OpenApiParameter("date_from", str, description="YYYY-MM-DD"),
    OpenApiParameter("date_to", str, description="YYYY-MM-DD inclusive"),
    OpenApiParameter("when", str, enum=["today", "tomorrow", "week"], description="arrivals_departures"),
    OpenApiParameter("status", str, enum=["due", "late", "all"], description="debts"),
    OpenApiParameter("days", int, description="ending_soon window (default 3)"),
    OpenApiParameter("q", str, description="audit_log: user, action, entity or id"),
    OpenApiParameter("room_type", str, description="room type id: revenue, debts, current_guests, arrivals_departures"),
    OpenApiParameter("method", str, enum=["cash", "bankak", "transfer"], description="revenue (collected), expenses"),
    OpenApiParameter("expense_category", str, description="expenses: supplies … other"),
    OpenApiParameter("category", str, enum=audit_rules.CATEGORY_KEYS, description="audit_log"),
]


def _is_manager(request) -> bool:
    return account_rules.is_manager(request.user.role)


class ReportIndexView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ReportIndexItemSerializer(many=True))
    def get(self, request):
        items = [
            {"name": d.name, "title": d.title, "badge": d.badge() if d.badge else None}
            for d in REGISTRY.values()
            if not d.manager_only
        ]
        return Response(ReportIndexItemSerializer(items, many=True).data)


class ReportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=REPORT_PARAMS, responses=ReportSerializer)
    def get(self, request, name):
        return Response(build(name, request.query_params, is_manager=_is_manager(request)).as_dict())


class ReportExportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[*REPORT_PARAMS, OpenApiParameter("format", str, enum=["xlsx", "csv"], required=True)],
        responses={
            (200, exporters.XLSX_TYPE): OpenApiResponse(OpenApiTypes.BINARY),
            (200, "text/csv"): OpenApiResponse(OpenApiTypes.BINARY),
        },
    )
    def get(self, request, name):
        fmt = request.query_params.get("format")
        if fmt not in ("xlsx", "csv"):
            raise ApiError("validation_error", 400, detail="الصيغة يجب أن تكون xlsx أو csv.")
        report = build(name, request.query_params, is_manager=_is_manager(request))
        settings = HotelSettings.load()
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
        if fmt == "xlsx":
            data = exporters.to_xlsx(report, decimals=settings.money_decimals, hotel_name=settings.name_ar)
            response = HttpResponse(data, content_type=exporters.XLSX_TYPE)
        else:
            response = HttpResponse(
                exporters.to_csv(report, decimals=settings.money_decimals), content_type="text/csv; charset=utf-8"
            )
        response["Content-Disposition"] = f'attachment; filename="skytowers-{name}-{stamp}.{fmt}"'
        return response


# --- Print documents ----------------------------------------------------------------------------


class InvoiceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=InvoiceDocumentSerializer, description="Data for the A4 invoice (artboard 7.1).")
    def get(self, request, pk):
        folio = get_object_or_404(
            Folio.objects.select_related("reservation__guest", "reservation__room", "reservation__room_type"), pk=pk
        )
        return Response(InvoiceDocumentSerializer(documents.invoice(folio, request.user)).data)


class PaymentReceiptView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=PaymentReceiptDocumentSerializer,
        description="Data for the 80 mm payment receipt (artboard 7.2).",
    )
    def get(self, request, pk):
        payment = get_object_or_404(
            Payment.objects.select_related(
                "folio__reservation__guest", "folio__reservation__room", "shift", "created_by"
            ),
            pk=pk,
        )
        return Response(PaymentReceiptDocumentSerializer(documents.payment_receipt(payment)).data)


class ExpenseReceiptView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=ExpenseReceiptDocumentSerializer,
        description="Data for the 80 mm expense slip (artboard 7.2).",
    )
    def get(self, request, pk):
        expense = get_object_or_404(Expense.objects.select_related("room", "created_by"), pk=pk)
        return Response(ExpenseReceiptDocumentSerializer(documents.expense_receipt(expense)).data)


class ShiftStatementView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=ShiftStatementDocumentSerializer,
        description="Data for the A4 shift statement (artboard 7.3).",
    )
    def get(self, request, pk):
        shift = get_object_or_404(Shift.objects.select_related("created_by", "closed_by"), pk=pk)
        return Response(ShiftStatementDocumentSerializer(documents.shift_statement(shift, request.user)).data)


class OwnerDashboardView(APIView):
    """Artboard 6.12 (spec §10.4 ``reports/owner-dashboard``): KPIs, 30-day occupancy, weekly revenue vs
    collected, «يحتاج انتباهك», and alert response per employee. Manager or owner only."""

    permission_classes = [IsManager]

    @extend_schema(
        parameters=[OpenApiParameter("period", str, enum=["month", "previous", "90days"])],
        responses=OwnerDashboardSerializer,
    )
    def get(self, request):
        period = request.query_params.get("period", "month")
        if period not in ("month", "previous", "90days"):
            raise ApiError("validation_error", 400, detail="الفترة يجب أن تكون month أو previous أو 90days.")
        return Response(OwnerDashboardSerializer(owner_dashboard(period)).data)
