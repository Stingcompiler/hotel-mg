from django.urls import path

from .views import ClockApproveView, SystemStatusView

urlpatterns = [
    path("status", SystemStatusView.as_view(), name="system-status"),
    path("clock/approve", ClockApproveView.as_view(), name="system-clock-approve"),
]
