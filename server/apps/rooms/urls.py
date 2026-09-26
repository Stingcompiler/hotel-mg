from django.urls import path

from . import views

room_type_urls = [
    path("", views.RoomTypeListView.as_view(), name="room-type-list"),
    path("<uuid:pk>", views.RoomTypeDetailView.as_view(), name="room-type-detail"),
]

urlpatterns = [
    path("", views.RoomListView.as_view(), name="room-list"),
    path("<uuid:pk>", views.RoomDetailView.as_view(), name="room-detail"),
    path("<uuid:pk>/set-status", views.RoomSetStatusView.as_view(), name="room-set-status"),
    path("<uuid:pk>/history", views.RoomHistoryView.as_view(), name="room-history"),
]
