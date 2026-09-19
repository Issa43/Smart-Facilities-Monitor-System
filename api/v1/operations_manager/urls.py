from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    AssetViewSet,
    FacilityViewSet,
    FaultViewSet,
    MaintenanceOrderViewSet,
    OperationalIncidentViewSet,
    OperationsMonitoringView,
    OperationsAssigneeView,
)


router = SimpleRouter()
router.register("facilities", FacilityViewSet, basename="operations-facility")
router.register("assets", AssetViewSet, basename="operations-asset")
router.register(
    "maintenance/orders",
    MaintenanceOrderViewSet,
    basename="operations-maintenance-order",
)
router.register("faults", FaultViewSet, basename="operations-fault")
router.register(
    "operations/incidents",
    OperationalIncidentViewSet,
    basename="operations-incident",
)

urlpatterns = [
    path(
        "operations/monitoring/",
        OperationsMonitoringView.as_view(),
        name="operations-monitoring",
    ),
    path("operations/assignees/", OperationsAssigneeView.as_view(), name="operations-assignees"),
    *router.urls,
]
