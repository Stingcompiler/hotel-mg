from django.urls import path

from . import views

urlpatterns = [
    path("", views.GuestListView.as_view(), name="guest-list"),
    path("<uuid:pk>", views.GuestDetailView.as_view(), name="guest-detail"),
    path("<uuid:pk>/documents", views.GuestDocumentUploadView.as_view(), name="guest-document-upload"),
    path("<uuid:pk>/documents/<uuid:doc_pk>", views.GuestDocumentView.as_view(), name="guest-document"),
]
