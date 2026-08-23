"""
Root URL configuration for SFLMS.

REST API only - no Django template views are exposed here except the
built-in Django admin (used only for internal data inspection, not by
the frontend client).
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.common.health import database_health, health, redis_health

urlpatterns = [
    # ---- Infrastructure health ----
    path("health/", health, name="health"),
    path("health/db/", database_health, name="health-db"),
    path("health/redis/", redis_health, name="health-redis"),

    path("admin/", admin.site.urls),

    # ---- Existing Phase 1 API routes ----
    path("api/auth/", include("apps.authentication.urls")),
    path("api/users/", include("apps.users.urls")),

    # ---- Versioned domain API composition root ----
    path("api/v1/", include("api.v1.urls", namespace="api_v1")),

    # ---- OpenAPI / Swagger documentation ----
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
