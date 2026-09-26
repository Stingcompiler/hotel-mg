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

stay_urls = [
    path("", views.CurrentStaysView.as_view(), name="stay-list"),
    path("check-in", views.CheckInView.as_view(), name="stay-check-in"),
    path("<uuid:pk>", views.StayDetailView.as_view(), name="stay-detail"),
    path("<uuid:pk>/extend/quote", views.ExtendQuoteView.as_view(), name="stay-extend-quote"),
    path("<uuid:pk>/extend", views.ExtendView.as_view(), name="stay-extend"),
    path("<uuid:pk>/change-room", views.ChangeRoomView.as_view(), name="stay-change-room"),
    path("<uuid:pk>/checkout", views.CheckoutView.as_view(), name="stay-checkout"),
    path("<uuid:pk>/cancel", views.CancelStayView.as_view(), name="stay-cancel"),
]
