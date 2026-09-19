from rest_framework.routers import SimpleRouter

from django.urls import path
from .views import CameraViewSet, IncidentViewSet, SafetyDocumentViewSet, SecurityAlertViewSet, SecurityAssigneeView, SecurityEvidenceViewSet, SecurityFacilityViewSet


router = SimpleRouter()
router.register(
    "security/alerts",
    SecurityAlertViewSet,
    basename="security-alert",
)
router.register(
    "security/incidents",
    IncidentViewSet,
    basename="security-incident",
)
router.register(
    "security/evidence",
    SecurityEvidenceViewSet,
    basename="security-evidence",
)
router.register("security/facilities", SecurityFacilityViewSet, basename="security-facility")
router.register("security/cameras", CameraViewSet, basename="security-camera")
router.register("security/documents", SafetyDocumentViewSet, basename="security-document")

urlpatterns = [path("security/assignees/", SecurityAssigneeView.as_view(), name="security-assignees"), *router.urls]
