from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import verify_manager_override
from apps.core.serializers import ReasonSerializer

from . import services
from .models import Folio, FolioLine, Payment
from .serializers import (
    FolioSerializer,
    LineCreateSerializer,
    PaymentCreateSerializer,
    PaymentSerializer,
    RefundSerializer,
)


def _folios():
    return Folio.objects.select_related("reservation__guest", "reservation__room")


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

    @extend_schema(request=ReasonSerializer, responses=FolioSerializer)
    def post(self, request, pk, line_pk):
        get_object_or_404(FolioLine, pk=line_pk, folio_id=pk)
        data = ReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.reverse_line(request.user, line_pk, **data.validated_data)
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

    @extend_schema(request=ReasonSerializer, responses={201: PaymentSerializer})
    def post(self, request, pk):
        get_object_or_404(Payment, pk=pk)
        data = ReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        reversal = services.reverse_payment(request.user, pk, **data.validated_data)
        return Response(PaymentSerializer(reversal).data, status=status.HTTP_201_CREATED)
