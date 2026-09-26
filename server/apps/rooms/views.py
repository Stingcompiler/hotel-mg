from django.db.models import Count
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsManager
from apps.accounts.services import require_confirmation

from . import services
from .models import Room, RoomType
from .serializers import (
    RoomCreateSerializer,
    RoomSerializer,
    RoomStatusHistorySerializer,
    RoomTypeSerializer,
    RoomTypeUpdateSerializer,
    RoomUpdateSerializer,
    SetStatusSerializer,
)


class ManagerWrites(IsAuthenticated):
    """Any signed-in user may read; writes need manager or owner."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return super().has_permission(request, view)
        return IsManager().has_permission(request, view)


def _room_types():
    return RoomType.objects.annotate(room_count=Count("rooms"))


class RoomTypeListView(APIView):
    permission_classes = [ManagerWrites]

    @extend_schema(responses=RoomTypeSerializer(many=True))
    def get(self, request):
        return Response(RoomTypeSerializer(_room_types(), many=True).data)

    @extend_schema(request=RoomTypeSerializer, responses={201: RoomTypeSerializer})
    def post(self, request):
        require_confirmation(request)  # sets prices (spec §6.8)
        data = RoomTypeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        room_type = services.create_room_type(request.user, **data.validated_data)
        return Response(RoomTypeSerializer(_room_types().get(pk=room_type.pk)).data, status=status.HTTP_201_CREATED)


class RoomTypeDetailView(APIView):
    permission_classes = [ManagerWrites]

    @extend_schema(request=RoomTypeUpdateSerializer, responses=RoomTypeSerializer)
    def patch(self, request, pk):
        room_type = get_object_or_404(RoomType, pk=pk)
        data = RoomTypeUpdateSerializer(room_type, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        changes = dict(data.validated_data)
        if services.PRICE_FIELDS & changes.keys():
            require_confirmation(request)
        services.update_room_type(request.user, pk, **changes)
        return Response(RoomTypeSerializer(_room_types().get(pk=pk)).data)


@extend_schema(
    parameters=[
        OpenApiParameter("floor", int),
        OpenApiParameter("status", str, enum=["ready", "occupied", "cleaning", "maintenance"]),
    ]
)
class RoomListView(ListAPIView):
    permission_classes = [ManagerWrites]
    serializer_class = RoomSerializer
    pagination_class = None  # 15-60 rooms: always the full list

    def get_queryset(self):
        qs = Room.objects.select_related("room_type").order_by("number")
        if floor := self.request.query_params.get("floor"):
            qs = qs.filter(floor=floor)
        if room_status := self.request.query_params.get("status"):
            qs = qs.filter(status=room_status)
        return qs

    @extend_schema(request=RoomCreateSerializer, responses={201: RoomSerializer})
    def post(self, request):
        data = RoomCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        room = services.create_room(request.user, **data.validated_data)
        return Response(RoomSerializer(room).data, status=status.HTTP_201_CREATED)


class RoomDetailView(APIView):
    permission_classes = [ManagerWrites]

    @extend_schema(responses=RoomSerializer)
    def get(self, request, pk):
        return Response(RoomSerializer(get_object_or_404(Room.objects.select_related("room_type"), pk=pk)).data)

    @extend_schema(request=RoomUpdateSerializer, responses=RoomSerializer)
    def patch(self, request, pk):
        room = get_object_or_404(Room, pk=pk)
        data = RoomUpdateSerializer(room, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        return Response(RoomSerializer(services.update_room(request.user, pk, **data.validated_data)).data)


class RoomSetStatusView(APIView):
    """Room board actions: confirm cleaned, start or end maintenance (any signed-in staff)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=SetStatusSerializer, responses=RoomSerializer)
    def post(self, request, pk):
        get_object_or_404(Room, pk=pk)
        data = SetStatusSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        room = services.set_status(request.user, pk, v["status"], reason=v["reason"], version=v.get("version"))
        return Response(RoomSerializer(room).data)


class RoomHistoryView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = RoomStatusHistorySerializer

    def get_queryset(self):
        room = get_object_or_404(Room, pk=self.kwargs["pk"])
        return room.status_history.select_related("created_by").order_by("-at")
