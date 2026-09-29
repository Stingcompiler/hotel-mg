from django.urls import path

from . import views

urlpatterns = [
    path("users", views.LoginUsersView.as_view(), name="auth-users"),
    path("pin", views.PinLoginView.as_view(), name="auth-pin"),
    path("password", views.PasswordLoginView.as_view(), name="auth-password"),
    path("recover", views.RecoverPasswordView.as_view(), name="auth-recover"),
    path("confirm", views.ConfirmView.as_view(), name="auth-confirm"),
    path("logout", views.LogoutView.as_view(), name="auth-logout"),
    path("me", views.MeView.as_view(), name="auth-me"),
]
