from django.urls import path

from . import views

urlpatterns = [
    path("", views.UserListView.as_view(), name="user-list"),
    path("<uuid:pk>", views.UserDetailView.as_view(), name="user-detail"),
    path("<uuid:pk>/reset-pin", views.ResetPinView.as_view(), name="user-reset-pin"),
    path("<uuid:pk>/unlock", views.UnlockView.as_view(), name="user-unlock"),
]
