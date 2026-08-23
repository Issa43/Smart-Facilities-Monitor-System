from rest_framework.routers import SimpleRouter

from .views import (
    DailyReportViewSet, FlatProjectPhaseViewSet, MaterialRequestViewSet, MaterialViewSet,
    ProjectDocumentViewSet, ProjectPhaseViewSet, QualityInspectionViewSet,
    ScopedProjectViewSet, SitePhotoViewSet,
)


router = SimpleRouter()
router.register("construction/projects", ScopedProjectViewSet, basename="construction-project")
router.register("construction/phases", FlatProjectPhaseViewSet, basename="construction-phase")
router.register("construction/materials", MaterialViewSet, basename="construction-material")
router.register("construction/material-requests", MaterialRequestViewSet, basename="construction-material-request")
router.register("construction/daily-reports", DailyReportViewSet, basename="construction-daily-report")
router.register("construction/quality-inspections", QualityInspectionViewSet, basename="construction-quality-inspection")
router.register("construction/documents", ProjectDocumentViewSet, basename="construction-document")
router.register("construction/site-photos", SitePhotoViewSet, basename="construction-site-photo")
router.register(
    (
        r"projects/(?P<project_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/phases"
    ),
    ProjectPhaseViewSet,
    basename="project-phase",
)

urlpatterns = router.urls
