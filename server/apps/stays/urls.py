from django.urls import path

from . import views

reservation_urls = [
    path("", views.ReservationListView.as_view(), name="reservation-list"),
    path("quote", views.QuoteView.as_view(), name="reservation-quote"),
    path("availability", views.AvailabilityView.as_view(), name="reservation-availability"),
    path("<uuid:pk>", views.ReservationDetailView.as_view(), name="reservation-detail"),
    path("<uuid:pk>/cancel", views.CancelReservationView.as_view(), name="reservation-cancel"),
    path("<uuid:pk>/no-show", views.NoShowView.as_view(), name="reservation-no-show"),
    path("<uuid:pk>/assign-room", views.AssignRoomView.as_view(), name="reservation-assign-room"),
]
