from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsManager
from apps.core import imaging
from apps.stays.models import ReservationStatus

from . import services, stats
from .models import Guest, GuestDocument
from .serializers import (
    DocumentUploadSerializer,
    GuestDocumentSerializer,
    GuestHistoryItemSerializer,
    GuestListItemSerializer,
    GuestSerializer,
    GuestUpdateSerializer,
    GuestWriteSerializer,
)


def _guests():
    return Guest.objects.prefetch_related("companions", "documents__created_by")


@extend_schema(
    parameters=[
        OpenApiParameter("q", str, description="Name (letter variants folded), phone digits, or exact ID number"),
        OpenApiParameter("warning", bool, description="Only guests with a warning note"),
        OpenApiParameter("debt", bool, description="Only guests with an open balance"),
        OpenApiParameter("in_house", bool, description="Only guests staying now"),
    ]
)
class GuestListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = GuestListItemSerializer

    def _flag(self, name) -> bool:
        return self.request.query_params.get(name) in ("1", "true")

    def get_queryset(self):
        qs = services.search(self.request.query_params.get("q", "")).prefetch_related(
            "companions", "documents__created_by"
        )
        if self._flag("warning"):
            qs = qs.exclude(warning_note="")
        if self._flag("in_house"):
            qs = qs.filter(reservations__status=ReservationStatus.CHECKED_IN).distinct()
        if self._flag("debt"):
            qs = qs.filter(pk__in=stats.debtor_ids())
        return qs

    def get_serializer(self, *args, **kwargs):
        if args and kwargs.get("many"):
            guests = list(args[0])
            kwargs["context"] = {**self.get_serializer_context(), "stats": stats.for_guests([g.pk for g in guests])}
            return self.serializer_class(guests, *args[1:], **kwargs)
        return super().get_serializer(*args, **kwargs)

    @extend_schema(request=GuestWriteSerializer, responses={201: GuestSerializer})
    def post(self, request):
        data = GuestWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        guest = services.create_guest(request.user, **data.validated_data)
        return Response(
            GuestSerializer(_guests().get(pk=guest.pk), context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class GuestDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=GuestSerializer)
    def get(self, request, pk):
        return Response(GuestSerializer(get_object_or_404(_guests(), pk=pk), context={"request": request}).data)

    @extend_schema(request=GuestUpdateSerializer, responses=GuestSerializer)
    def patch(self, request, pk):
        get_object_or_404(Guest, pk=pk)
        data = GuestUpdateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.update_guest(request.user, pk, **data.validated_data)
        return Response(GuestSerializer(_guests().get(pk=pk), context={"request": request}).data)


class GuestHistoryView(APIView):
    """Guest profile «سجل الإقامات»: every reservation, newest first, with its balance."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=GuestHistoryItemSerializer(many=True))
    def get(self, request, pk):
        get_object_or_404(Guest, pk=pk)
        return Response(GuestHistoryItemSerializer(stats.history(pk), many=True).data)


class GuestDocumentUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    @extend_schema(request=DocumentUploadSerializer, responses={201: GuestDocumentSerializer})
    def post(self, request, pk):
        get_object_or_404(Guest, pk=pk)
        data = DocumentUploadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        imaging.check_upload_size(data.validated_data["file"].size)  # before reading (C-17)
        document = services.add_document(request.user, pk, data.validated_data["file"].read())
        return Response(GuestDocumentSerializer(document).data, status=status.HTTP_201_CREATED)


class GuestDocumentView(APIView):
    """The unblurred ID image. Manager/owner only; every view is audited."""

    permission_classes = [IsManager]

    @extend_schema(responses={(200, "image/jpeg"): OpenApiResponse(OpenApiTypes.BINARY)})
    def get(self, request, pk, doc_pk):
        get_object_or_404(GuestDocument, pk=doc_pk, guest_id=pk)
        document, data = services.open_document(request.user, doc_pk)
        response = HttpResponse(data, content_type=document.content_type)
        response["Cache-Control"] = "no-store"
        return response
