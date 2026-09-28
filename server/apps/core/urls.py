from django.urls import path

from .views import AlertSoundView, ClockApproveView, HotelSettingsView, SystemStatusView

urlpatterns = [
    path("status", SystemStatusView.as_view(), name="system-status"),
    path("clock/approve", ClockApproveView.as_view(), name="system-clock-approve"),
    path("settings", HotelSettingsView.as_view(), name="system-settings"),
    path("alert-sound", AlertSoundView.as_view(), name="system-alert-sound"),
]
