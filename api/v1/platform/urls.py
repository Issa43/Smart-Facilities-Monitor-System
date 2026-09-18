from django.urls import path
from rest_framework.routers import SimpleRouter
from .views import AuditLogViewSet, DeviceRegistrationViewSet, NotificationViewSet, SystemSettingViewSet

router = SimpleRouter()
router.register("notifications", NotificationViewSet, basename="notification")
router.register("audit-logs", AuditLogViewSet, basename="audit-log")
router.register("settings", SystemSettingViewSet, basename="system-setting")
device_list = DeviceRegistrationViewSet.as_view({"get": "list", "post": "create"})
device_detail = DeviceRegistrationViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
)

urlpatterns = [
    path(
        "notifications/devices/",
        device_list,
        name="notification-device-list",
    ),
    path(
        "notifications/devices/<uuid:pk>/",
        device_detail,
        name="notification-device-detail",
    ),
] + router.urls
