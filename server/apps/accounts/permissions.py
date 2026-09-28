from rest_framework.permissions import BasePermission

from . import rules


class IsOwner(BasePermission):
    """The owner only (owner decision 2026-09-28: the owner sets the accepted currencies and their rates)."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == "owner")


class IsManager(BasePermission):
    """Manager or owner (spec §6.8: settings, users, overrides)."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and rules.is_manager(user.role))
