from django.contrib import admin

from apps.core.admin import ReadOnlyAdmin

from .models import User


@admin.register(User)
class UserAdmin(ReadOnlyAdmin):
    list_display = ("username", "full_name", "role", "is_active", "last_login")
    list_filter = ("role", "is_active")
    search_fields = ("username", "full_name")
    exclude = ("password", "pin_hash")
