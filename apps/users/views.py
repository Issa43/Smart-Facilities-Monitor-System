from django.contrib.auth.hashers import check_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Role, User
from .permissions import IsSuperAdminForWrite
from .serializers import (
    RoleSerializer,
    UserCreateSerializer,
    UserSelfUpdateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)


class RoleViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Roles are fixed by the approved architecture (the 4 SFLMS roles) and are
    seeded via migration/data command, not created ad-hoc through the API -
    hence read-only here. Every authenticated user may list roles (e.g. to
    populate a dropdown), but nothing else.
    """

    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["name"]
    search_fields = ["name", "description"]


class UserViewSet(viewsets.ModelViewSet):
    """
    Full CRUD restricted to Super Admin (architecture §6 permission matrix).
    Every authenticated user can read/update limited fields of their own
    profile via the `me` action regardless of role.
    """

    queryset = User.objects.select_related("role").all()
    permission_classes = [IsSuperAdminForWrite]
    filterset_fields = ["role", "status"]
    search_fields = ["full_name", "email", "username", "phone"]
    ordering_fields = ["created_at", "full_name"]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action in ("update", "partial_update"):
            return UserUpdateSerializer
        return UserSerializer

    @action(detail=False, methods=["get", "patch"], permission_classes=[IsAuthenticated])
    def me(self, request):
        """GET/PATCH the currently authenticated user's own profile."""
        if request.method == "GET":
            return Response(UserSerializer(request.user).data)

        serializer = UserSelfUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        user = request.user
        old_password = request.data.get("old_password", "")
        new_password = request.data.get("new_password", "")

        if not check_password(old_password, user.password):
            raise ValidationError({"old_password": ["Old password is incorrect."]})
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as exc:
            raise ValidationError({"new_password": exc.messages}) from exc

        user.set_password(new_password)
        user.save(update_fields=["password"])
        return Response({"detail": "Password updated successfully."})
