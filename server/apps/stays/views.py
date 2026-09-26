from datetime import timedelta

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rooms.models import RoomType

from . import services
from .models import Reservation
from .serializers import (
    AssignRoomSerializer,
    AvailableRoomSerializer,
    QuoteRequestSerializer,
    QuoteSerializer,
    ReasonSerializer,
    ReservationCreateSerializer,
    ReservationSerializer,
    VersionSerializer,
)


def _reservations():
    return Reservation.objects.select_related("guest", "room", "room_type")


class QuoteView(APIView):
    """Nights, end date and pricing options (e.g. 1 week + 3 nights vs 10 nights) for the booking form."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=QuoteRequestSerializer, responses=QuoteSerializer)
    def post(self, request):
        data = QuoteRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(QuoteSerializer(services.quote(**data.validated_data)).data)


class AvailabilityQuery(serializers.Serializer):
    room_type = serializers.PrimaryKeyRelatedField(queryset=RoomType.objects.all(), required=False)
    date_from = serializers.DateField()
    date_to = serializers.DateField(help_text="Exclusive (the check-out date).")

    def validate(self, attrs):
        if attrs["date_to"] <= attrs["date_from"]:
            raise serializers.ValidationError({"date_to": "تاريخ المغادرة يجب أن يكون بعد تاريخ الوصول."})
        return attrs


class AvailabilityView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[AvailabilityQuery], responses=AvailableRoomSerializer(many=True))
    def get(self, request):
        q = AvailabilityQuery(data=request.query_params)
        q.is_valid(raise_exception=True)
        v = q.validated_data
        rooms = services.available_rooms(v.get("room_type"), v["date_from"], v["date_to"])
        return Response(AvailableRoomSerializer(rooms, many=True).data)


@extend_schema(
    parameters=[
        OpenApiParameter("date_from", str, description="YYYY-MM-DD; default today"),
        OpenApiParameter("date_to", str, description="YYYY-MM-DD exclusive; default date_from + 14 days"),
        OpenApiParameter("status", str, many=True),
    ]
)
class ReservationListView(ListAPIView):
    """Reservations touching the window (timeline and list views)."""

    permission_classes = [IsAuthenticated]
    serializer_class = ReservationSerializer
    pagination_class = None

    def get_queryset(self):
        params = self.request.query_params
        field = serializers.DateField()
        date_from = field.to_internal_value(params["date_from"]) if "date_from" in params else services.today()
        date_to = field.to_internal_value(params["date_to"]) if "date_to" in params else date_from + timedelta(days=14)
        qs = services.window(date_from, date_to).select_related("guest", "room", "room_type")
        if statuses := params.getlist("status"):
            qs = qs.filter(status__in=statuses)
        return qs.order_by("check_in_date", "room__number")

    @extend_schema(request=ReservationCreateSerializer, responses={201: ReservationSerializer})
    def post(self, request):
        data = ReservationCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        reservation = services.create_reservation(request.user, **data.validated_data)
        return Response(ReservationSerializer(_reservations().get(pk=reservation.pk)).data,
                        status=status.HTTP_201_CREATED)  # fmt: skip


class ReservationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ReservationSerializer)
    def get(self, request, pk):
        return Response(ReservationSerializer(get_object_or_404(_reservations(), pk=pk)).data)


class CancelReservationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ReasonSerializer, responses=ReservationSerializer)
    def post(self, request, pk):
        get_object_or_404(Reservation, pk=pk)
        data = ReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.cancel_reservation(request.user, pk, **data.validated_data)
        return Response(ReservationSerializer(_reservations().get(pk=pk)).data)


class NoShowView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=VersionSerializer, responses=ReservationSerializer)
    def post(self, request, pk):
        get_object_or_404(Reservation, pk=pk)
        data = VersionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.mark_no_show(request.user, pk, **data.validated_data)
        return Response(ReservationSerializer(_reservations().get(pk=pk)).data)


class AssignRoomView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=AssignRoomSerializer, responses=ReservationSerializer)
    def post(self, request, pk):
        get_object_or_404(Reservation, pk=pk)
        data = AssignRoomSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.assign_room(request.user, pk, **data.validated_data)
        return Response(ReservationSerializer(_reservations().get(pk=pk)).data)
