from rest_framework.routers import DefaultRouter

from .views import RoleViewSet, UserViewSet

router = DefaultRouter()
router.register("roles", RoleViewSet, basename="role")
router.register("", UserViewSet, basename="user")

urlpatterns = router.urls
