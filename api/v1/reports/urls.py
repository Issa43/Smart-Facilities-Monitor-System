from rest_framework.routers import SimpleRouter

from .views import ReportRequestViewSet, ReportTemplateViewSet


router = SimpleRouter()
router.register(
    "reports/templates",
    ReportTemplateViewSet,
    basename="report-template",
)
router.register(
    "reports/requests",
    ReportRequestViewSet,
    basename="report-request",
)

urlpatterns = router.urls
