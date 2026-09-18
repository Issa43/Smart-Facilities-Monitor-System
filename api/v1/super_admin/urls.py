from rest_framework.routers import DefaultRouter

from .views import AIIngestionCredentialViewSet, ProjectViewSet


router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")
router.register(
    "admin/ai-ingestion-credentials",
    AIIngestionCredentialViewSet,
    basename="ai-ingestion-credential",
)

urlpatterns = router.urls
