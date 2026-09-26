from datetime import timedelta

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rooms.models import RoomType

from . import rules, services, stay_services
from .board import board
from .models import Reservation, Stay
from .serializers import (
    AssignRoomSerializer,
    AvailableRoomSerializer,
    CancelOptionsSerializer,
    CancelReservationSerializer,
    CancelStaySerializer,
    ChangeRoomOptionSerializer,
    ChangeRoomSerializer,
    CheckInSerializer,
    CheckoutSerializer,
    ExtendQuoteRequestSerializer,
    ExtendQuoteSerializer,
    ExtendSerializer,
    QuoteRequestSerializer,
    QuoteSerializer,
    ReservationCreateSerializer,
    ReservationSerializer,
    RoomBoardSerializer,
    StayDetailSerializer,
    StaySerializer,
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
        qs = (
            services.window(date_from, date_to)
            .select_related("guest", "room", "room_type", "folio", "stay")
            .annotate(
                deposit_total=Coalesce(Sum("folio__payments__amount", filter=Q(folio__payments__kind="deposit")), 0)
            )
        )
        if statuses := params.getlist("status"):
            qs = qs.filter(status__in=statuses)
        return qs.order_by("check_in_date", "room__number")

    @extend_schema(request=ReservationCreateSerializer, responses={201: ReservationSerializer})
    def post(self, request):
        data = ReservationCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        booking = dict(data.validated_data)
        if booking.pop("check_in_now"):
            reservation = stay_services.book_and_check_in(request.user, **booking).reservation
        else:
            reservation = services.create_reservation(request.user, **booking)
        return Response(
            ReservationSerializer(_reservations().get(pk=reservation.pk)).data, status=status.HTTP_201_CREATED
        )


class ReservationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ReservationSerializer)
    def get(self, request, pk):
        return Response(ReservationSerializer(get_object_or_404(_reservations(), pk=pk)).data)


class CancelReservationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=CancelReservationSerializer, responses=ReservationSerializer)
    def post(self, request, pk):
        get_object_or_404(Reservation, pk=pk)
        data = CancelReservationSerializer(data=request.data)
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


# --- Stays -----------------------------------------------------------------------------------


def _stays():
    return Stay.objects.select_related(
        "reservation__guest", "reservation__room", "reservation__room_type", "override_by"
    ).prefetch_related("segments__room")


def _stay_response(stay_id, code=status.HTTP_200_OK):
    return Response(StaySerializer(_stays().get(pk=stay_id)).data, status=code)


class CurrentStaysView(ListAPIView):
    """Guests in house now."""

    permission_classes = [IsAuthenticated]
    serializer_class = StaySerializer
    pagination_class = None

    def get_queryset(self):
        return _stays().filter(reservation__status="checked_in").order_by("reservation__room__number")


class CheckInView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=CheckInSerializer, responses={201: StaySerializer})
    def post(self, request):
        data = CheckInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        stay = stay_services.check_in(request.user, v["reservation"].pk, room=v.get("room"), version=v.get("version"))
        return _stay_response(stay.pk, status.HTTP_201_CREATED)


class StayDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=StayDetailSerializer)
    def get(self, request, pk):
        get_object_or_404(Stay, pk=pk)
        stay = _stays().prefetch_related("reservation__guest__companions").get(pk=pk)
        return Response(StayDetailSerializer(stay, context={"request": request}).data)


class ExtendQuoteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ExtendQuoteRequestSerializer, responses=ExtendQuoteSerializer)
    def post(self, request, pk):
        stay = get_object_or_404(_stays(), pk=pk)
        data = ExtendQuoteRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(ExtendQuoteSerializer(stay_services.extension_quote(stay, **data.validated_data)).data)


class ExtendView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ExtendSerializer, responses=StaySerializer)
    def post(self, request, pk):
        get_object_or_404(Stay, pk=pk)
        data = ExtendSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        stay_services.extend(request.user, pk, **data.validated_data)
        return _stay_response(pk)


class ChangeRoomView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ChangeRoomOptionSerializer(many=True))
    def get(self, request, pk):
        """Rooms the guest can move to, same type first, with the price difference."""
        stay = get_object_or_404(_stays(), pk=pk)
        options = [{"room": room, "difference": diff} for room, diff in stay_services.change_room_candidates(stay)]
        return Response(ChangeRoomOptionSerializer(options, many=True).data)

    @extend_schema(request=ChangeRoomSerializer, responses=StaySerializer)
    def post(self, request, pk):
        get_object_or_404(Stay, pk=pk)
        data = ChangeRoomSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        stay_services.change_room(request.user, pk, **data.validated_data)
        return _stay_response(pk)


class CheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=CheckoutSerializer, responses=StaySerializer)
    def post(self, request, pk):
        get_object_or_404(Stay, pk=pk)
        data = CheckoutSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        stay_services.checkout(request.user, pk, **data.validated_data)
        return _stay_response(pk)


class CancelStayView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=CancelOptionsSerializer)
    def get(self, request, pk):
        """Settlement choices for the nights already used."""
        stay = get_object_or_404(_stays(), pk=pk)
        used, options = stay_services.cancel_options(stay)
        return Response(
            CancelOptionsSerializer(
                {
                    "nights_used": used,
                    "current_total": stay.reservation.total,
                    "options": [{"key": o.key, "label": rules.option_label(o), "total": total} for o, total in options],
                }
            ).data
        )

    @extend_schema(request=CancelStaySerializer, responses=StaySerializer)
    def post(self, request, pk):
        get_object_or_404(Stay, pk=pk)
        data = CancelStaySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        stay_services.cancel_stay(request.user, pk, **data.validated_data)
        return _stay_response(pk)


class RoomBoardView(APIView):
    """Room board 6.2 (spec §10.4 ``rooms?view=board``, typed): every room with its state, current stay, next
    booking and the summary tiles. Polled every 15 s. Served at ``rooms/board``; lives here because the board
    reads stays (rooms must not depend on stays)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=RoomBoardSerializer, operation_id="rooms_board")
    def get(self, request):
        return Response(RoomBoardSerializer(board()).data)
