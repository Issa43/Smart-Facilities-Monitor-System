from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    AuthorizedVehicleViewSet,
    CameraActiveModelDetailView,
    CameraActiveModelsView,
    CameraROIViewSet,
    RestrictedScheduleViewSet,
    VirtualLineViewSet,
)


router = SimpleRouter()
router.register("roi", CameraROIViewSet, basename="camera-roi")
router.register(
    "restricted-schedules",
    RestrictedScheduleViewSet,
    basename="restricted-schedule",
)
router.register("virtual-lines", VirtualLineViewSet, basename="virtual-line")
router.register(
    "vehicles/authorized",
    AuthorizedVehicleViewSet,
    basename="authorized-vehicle",
)

urlpatterns = [
    path(
        "cameras/<uuid:camera_id>/active-models/",
        CameraActiveModelsView.as_view(),
        name="camera-active-models",
    ),
    path(
        "cameras/<uuid:camera_id>/active-models/<str:model_identifier>/",
        CameraActiveModelDetailView.as_view(),
        name="camera-active-model-detail",
    ),
    *router.urls,
]
