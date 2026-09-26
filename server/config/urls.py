from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.rooms.urls import room_type_urls
from apps.stays.urls import reservation_urls

api_v1 = [
    path("schema", SpectacularAPIView.as_view(), name="schema"),
    path("schema/swagger/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("system/", include("apps.core.urls")),
    path("auth/", include("apps.accounts.urls")),
    path("users/", include("apps.accounts.urls_users")),
    path("audit/", include("apps.audit.urls")),
    path("room-types/", include(room_type_urls)),
    path("rooms/", include("apps.rooms.urls")),
    path("guests/", include("apps.guests.urls")),
    path("reservations/", include(reservation_urls)),
]

urlpatterns = [
    path("api/v1/", include(api_v1)),
    # Staff-only verification UI during the backend phases (spec §12).
    path("admin/", admin.site.urls),
]
