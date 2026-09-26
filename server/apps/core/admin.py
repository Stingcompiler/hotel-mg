from django.contrib import admin


class ReadOnlyAdmin(admin.ModelAdmin):
    """Django admin is a staff-only viewer during the backend phases; all writes go through services."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
