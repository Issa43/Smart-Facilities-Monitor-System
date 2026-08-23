from rest_framework.routers import SimpleRouter
from .views import AuditLogViewSet, NotificationViewSet, SystemSettingViewSet

router = SimpleRouter()
router.register("notifications", NotificationViewSet, basename="notification")
router.register("audit-logs", AuditLogViewSet, basename="audit-log")
router.register("settings", SystemSettingViewSet, basename="system-setting")
urlpatterns = router.urls
