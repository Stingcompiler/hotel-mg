from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsOwner
from apps.accounts.services import verify_manager_override

from . import services
from .models import Currency, Folio, FolioLine, Payment
from .serializers import (
    CurrencyCreateSerializer,
    CurrencySerializer,
    CurrencyUpdateSerializer,
    FolioSerializer,
    LineCreateSerializer,
    PaymentCreateSerializer,
    PaymentSerializer,
    RefundSerializer,
    ReversalSerializer,
)


def _folios():
    return Folio.objects.select_related("reservation__guest", "reservation__room")


def _approval(data: dict):
    """(reason, approving manager or None) — a wrong password counts towards the managers' lockout (decision 150)."""
    password = data.get("manager_password") or ""
    return data["reason"], verify_manager_override(password, data["reason"]) if password else None


def _folio_response(folio_id, code=status.HTTP_200_OK):
    return Response(FolioSerializer(_folios().get(pk=folio_id)).data, status=code)


class FolioDetailView(APIView):
    """Totals and the ledger with running balance (artboard 6.5 «الفاتورة»)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=FolioSerializer)
    def get(self, request, pk):
        get_object_or_404(Folio, pk=pk)
        return _folio_response(pk)


class FolioLineView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LineCreateSerializer, responses={201: FolioSerializer})
    def post(self, request, pk):
        get_object_or_404(Folio, pk=pk)
        data = LineCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = dict(data.validated_data)
        password, manager_reason = v.pop("manager_password"), v.pop("manager_reason")
        approver = verify_manager_override(password, manager_reason or v["reason"]) if password else None
        services.add_line(request.user, pk, approver=approver, **v)
        return _folio_response(pk, status.HTTP_201_CREATED)


class ReverseLineView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ReversalSerializer, responses=FolioSerializer)
    def post(self, request, pk, line_pk):
        get_object_or_404(FolioLine, pk=line_pk, folio_id=pk)
        data = ReversalSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        reason, approver = _approval(data.validated_data)
        services.reverse_line(request.user, line_pk, reason=reason, approver=approver)
        return _folio_response(pk)


class PaymentCreateView(APIView):
    """Needs an open shift on this device (409 ``no_open_shift``)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=PaymentCreateSerializer, responses={201: PaymentSerializer})
    def post(self, request, pk):
        get_object_or_404(Folio, pk=pk)
        data = PaymentCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        payment = services.record_payment(request.user, pk, **data.validated_data)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class RefundView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=RefundSerializer, responses={201: PaymentSerializer})
    def post(self, request, pk):
        get_object_or_404(Folio, pk=pk)
        data = RefundSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        payment = services.refund(request.user, pk, **data.validated_data)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class PaymentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=PaymentSerializer)
    def get(self, request, pk):
        return Response(PaymentSerializer(get_object_or_404(Payment.objects.select_related("created_by"), pk=pk)).data)


class ReversePaymentView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ReversalSerializer, responses={201: PaymentSerializer})
    def post(self, request, pk):
        get_object_or_404(Payment, pk=pk)
        data = ReversalSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        reason, approver = _approval(data.validated_data)
        reversal = services.reverse_payment(request.user, pk, reason=reason, approver=approver)
        return Response(PaymentSerializer(reversal).data, status=status.HTTP_201_CREATED)


# --- Currencies -----------------------------------------------------------------------------------


class CurrencyListView(APIView):
    """Everyone signed in reads the accepted currencies (payment dialogs); only the owner adds one."""

    def get_permissions(self):
        return [IsOwner()] if self.request.method == "POST" else [IsAuthenticated()]

    @extend_schema(responses=CurrencySerializer(many=True))
    def get(self, request):
        return Response(CurrencySerializer(Currency.objects.all(), many=True).data)

    @extend_schema(request=CurrencyCreateSerializer, responses={201: CurrencySerializer})
    def post(self, request):
        data = CurrencyCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        row = services.create_currency(request.user, **data.validated_data)
        return Response(CurrencySerializer(row).data, status=status.HTTP_201_CREATED)


class CurrencyDetailView(APIView):
    permission_classes = [IsOwner]

    @extend_schema(request=CurrencyUpdateSerializer, responses=CurrencySerializer)
    def patch(self, request, pk):
        get_object_or_404(Currency, pk=pk)
        data = CurrencyUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        return Response(CurrencySerializer(services.update_currency(request.user, pk, **data.validated_data)).data)
