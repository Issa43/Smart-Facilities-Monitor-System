"""Root router composition for version 1 domain APIs."""

from django.urls import include, path


app_name = "v1"

urlpatterns = [
    path("", include("api.v1.ai_configuration.urls")),
    path("", include("api.v1.camera_events.urls")),
    path("", include("api.v1.analytics.urls")),
    path("auth/", include("apps.authentication.urls")),
    path("users/", include("apps.users.urls")),
    path("", include("api.v1.construction_manager.urls")),
    path("", include("api.v1.operations_manager.urls")),
    path("", include("api.v1.reports.urls")),
    path("", include("api.v1.security_officer.urls")),
    path("", include("api.v1.super_admin.urls")),
    path("", include("api.v1.platform.urls")),
    path("", include("api.v1.safety.urls")),
]
