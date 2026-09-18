from rest_framework.routers import SimpleRouter

from .views import CameraEventViewSet


router = SimpleRouter()
router.register("camera-events", CameraEventViewSet, basename="camera-event")

urlpatterns = router.urls
