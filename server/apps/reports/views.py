from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import Folio, Payment
from apps.cash.models import Expense, Shift
from apps.core.errors import ApiError
from apps.core.models import HotelSettings

from . import documents, exporters, queries  # noqa: F401  (queries registers the reports)
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
    meta = serializers.DictField(help_text="title, as_of, date_from, date_to, formula, note, tiles, totals")


REPORT_PARAMS = [
    OpenApiParameter("date_from", str, description="YYYY-MM-DD"),
    OpenApiParameter("date_to", str, description="YYYY-MM-DD inclusive"),
    OpenApiParameter("when", str, enum=["today", "tomorrow", "week"], description="arrivals_departures"),
    OpenApiParameter("status", str, enum=["due", "late", "all"], description="debts"),
    OpenApiParameter("days", int, description="ending_soon window (default 3)"),
]


class ReportIndexView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ReportIndexItemSerializer(many=True))
    def get(self, request):
        items = [{"name": d.name, "title": d.title, "badge": d.badge() if d.badge else None} for d in REGISTRY.values()]
        return Response(ReportIndexItemSerializer(items, many=True).data)


class ReportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=REPORT_PARAMS, responses=ReportSerializer)
    def get(self, request, name):
        return Response(build(name, request.query_params).as_dict())


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
        report = build(name, request.query_params)
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

    @extend_schema(responses=OpenApiTypes.OBJECT, description="Data for the A4 invoice (artboard 7.1).")
    def get(self, request, pk):
        folio = get_object_or_404(
            Folio.objects.select_related("reservation__guest", "reservation__room", "reservation__room_type"), pk=pk
        )
        return Response(documents.invoice(folio, request.user))


class PaymentReceiptView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT, description="Data for the 80 mm payment receipt (artboard 7.2).")
    def get(self, request, pk):
        payment = get_object_or_404(
            Payment.objects.select_related(
                "folio__reservation__guest", "folio__reservation__room", "shift", "created_by"
            ),
            pk=pk,
        )
        return Response(documents.payment_receipt(payment))


class ExpenseReceiptView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT, description="Data for the 80 mm expense slip (artboard 7.2).")
    def get(self, request, pk):
        return Response(
            documents.expense_receipt(get_object_or_404(Expense.objects.select_related("room", "created_by"), pk=pk))
        )


class ShiftStatementView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT, description="Data for the A4 shift statement (artboard 7.3).")
    def get(self, request, pk):
        shift = get_object_or_404(Shift.objects.select_related("created_by", "closed_by"), pk=pk)
        return Response(documents.shift_statement(shift, request.user))
