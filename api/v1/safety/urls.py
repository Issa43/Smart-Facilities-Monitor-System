from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    HazardEventViewSet,
    ProjectSafetyAlertViewSet,
    SafetyActionProposalViewSet,
    SafetyMonitoringCoverageView,
)


router = SimpleRouter()
router.register("safety/alerts", ProjectSafetyAlertViewSet, basename="safety-alert")
router.register(
    "safety/action-proposals",
    SafetyActionProposalViewSet,
    basename="safety-action-proposal",
)
router.register("safety/hazard-events", HazardEventViewSet, basename="safety-hazard-event")

urlpatterns = [
    path(
        "safety/monitoring-coverage/",
        SafetyMonitoringCoverageView.as_view(),
        name="safety-monitoring-coverage",
    ),
    *router.urls,
]
