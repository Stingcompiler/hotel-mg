from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

api_v1 = [
    path("schema", SpectacularAPIView.as_view(), name="schema"),
    path("schema/swagger/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("system/", include("apps.core.urls")),
]

urlpatterns = [
    path("api/v1/", include(api_v1)),
    # Staff-only verification UI during the backend phases (spec §12).
    path("admin/", admin.site.urls),
]
