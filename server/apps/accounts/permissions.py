from rest_framework.permissions import BasePermission

from . import rules


class IsManager(BasePermission):
    """Manager or owner (spec §6.8: settings, users, overrides)."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and rules.is_manager(user.role))
