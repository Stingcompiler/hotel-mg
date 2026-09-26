from django.urls import path

from . import views

urlpatterns = [
    path("", views.AuditLogListView.as_view(), name="audit-list"),
    path("verify", views.AuditVerifyView.as_view(), name="audit-verify"),
]
