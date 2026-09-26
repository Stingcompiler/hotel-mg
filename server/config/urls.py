from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.backup.urls import backup_urls, owner_urls
from apps.billing.urls import folio_urls, payment_urls
from apps.cash.urls import expense_urls, shift_urls
from apps.core import spa
from apps.reports.urls import document_urls, report_urls
from apps.rooms.urls import room_type_urls
from apps.stays.urls import reservation_urls, room_board_urls, stay_urls

api_v1 = [
    path("schema", SpectacularAPIView.as_view(), name="schema"),
    path("schema/swagger/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("system/", include("apps.core.urls")),
    path("auth/", include("apps.accounts.urls")),
    path("users/", include("apps.accounts.urls_users")),
    path("audit/", include("apps.audit.urls")),
    path("room-types/", include(room_type_urls)),
    path("rooms/", include(room_board_urls)),
    path("rooms/", include("apps.rooms.urls")),
    path("guests/", include("apps.guests.urls")),
    path("reservations/", include(reservation_urls)),
    path("stays/", include(stay_urls)),
    path("folios/", include(folio_urls)),
    path("payments/", include(payment_urls)),
    path("shifts/", include(shift_urls)),
    path("expenses/", include(expense_urls)),
    path("reports/", include(report_urls)),
    path("followups/", include("apps.followups.urls")),
    path("backup/", include(backup_urls)),
    path("owner/", include(owner_urls)),
    path("", include(document_urls)),
]

handler404 = "apps.core.errors.api_not_found"

urlpatterns = [
    path("api/v1/", include(api_v1)),
    # Staff-only verification UI during the backend phases (spec §12).
    path("admin/", admin.site.urls),
    # The SPA (F3): hashed assets, then index.html for every client route. Unknown API paths stay 404 JSON.
    path("assets/<path:path>", spa.asset),
    re_path(r"^(?!api/|admin/|static/)(?P<path>.*)$", spa.index),
]
