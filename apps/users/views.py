from django.contrib.auth.hashers import check_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit.services import record_audit
from apps.notifications.services import setting_enabled
from apps.common.permissions import IsSuperAdmin

from .models import Permission, Role, User
from .permissions import IsSuperAdminForWrite
from .serializers import (
    RoleSerializer,
    RolePermissionUpdateSerializer,
    UserCreateSerializer,
    UserSelfUpdateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)


class RoleViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Roles are fixed by the approved architecture (the 4 SFLMS roles) and are
    seeded via migration/data command, not created ad-hoc through the API -
    hence read-only here. The catalogue and permission matrix are restricted
    to Super Admin with the rest of Users/Roles management.
    """

    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [IsSuperAdmin]
    filterset_fields = ["name"]
    search_fields = ["name", "description"]

    @action(
        detail=True,
        methods=["put"],
        url_path="permissions",
        permission_classes=[IsSuperAdmin],
    )
    @transaction.atomic
    def set_permissions(self, request, pk=None):
        role = self.get_object()
        if role.name == Role.SUPER_ADMIN:
            raise ValidationError(
                {
                    "permissions": [
                        "Super Admin is a protected break-glass role and always has full access."
                    ]
                }
            )
        payload = RolePermissionUpdateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        before = list(
            role.permissions.order_by("permission_name").values_list(
                "permission_name", flat=True
            )
        )
        Permission.objects.filter(role=role).exclude(
            permission_name__in=payload.validated_data["permissions"]
        ).delete()
        Permission.objects.bulk_create(
            [
                Permission(role=role, permission_name=name)
                for name in payload.validated_data["permissions"]
            ],
            ignore_conflicts=True,
        )
        record_audit(
            actor=request.user,
            action="role.permissions.updated",
            entity=role,
            before={"permissions": before},
            after={"permissions": payload.validated_data["permissions"]},
            request=request,
        )
        role = Role.objects.prefetch_related("permissions").get(pk=role.pk)
        return Response(RoleSerializer(role).data, status=status.HTTP_200_OK)


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

    def get_queryset(self):
        queryset = User.objects.select_related("role")
        # Machine principals (AI ingestion service accounts) are created with
        # no role, cannot authenticate with a password, and are denied by every
        # RBAC check. Listing them broke each client that requires a role and
        # offered non-human accounts in assignee pickers, so they are omitted
        # from the listing — keeping `count` and pagination consistent with the
        # rows actually returned. Detail routes are deliberately unchanged, so
        # the existing rule that rejects giving a principal a human role still
        # applies exactly as before.
        if getattr(self, "action", None) == "list":
            queryset = queryset.exclude(role__isnull=True)
        user = self.request.user
        if not user.is_authenticated or not user.role_id:
            return queryset.none()
        if user.role.name == Role.SUPER_ADMIN:
            return queryset.all()
        if user.role.name == Role.CONSTRUCTION_MANAGER:
            project_ids = user.project_assignments.filter(
                is_active=True
            ).values("project_id")
            return queryset.filter(
                Q(pk=user.pk)
                | Q(project_assignments__project_id__in=project_ids, project_assignments__is_active=True)
            ).distinct()
        facility_ids = user.facility_assignments.filter(
            is_active=True
        ).values("facility_id")
        return queryset.filter(
            Q(pk=user.pk)
            | Q(facility_assignments__facility_id__in=facility_ids, facility_assignments__is_active=True)
        ).distinct()

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action in ("update", "partial_update"):
            return UserUpdateSerializer
        return UserSerializer

    def create(self, request, *args, **kwargs):
        write_serializer = self.get_serializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        user = write_serializer.save()
        response_data = UserSerializer(
            user,
            context=self.get_serializer_context(),
        ).data
        headers = self.get_success_headers(response_data)
        return Response(
            response_data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        if instance.pk == request.user.pk:
            errors = {}
            if (
                "role" in request.data
                and str(request.data["role"]) != str(instance.role_id)
            ):
                errors["role"] = [
                    "You cannot change your own Super Admin role."
                ]
            if (
                "status" in request.data
                and request.data["status"] != User.STATUS_ACTIVE
            ):
                errors["status"] = [
                    "You cannot suspend or deactivate your own Super Admin account."
                ]
            if errors:
                raise ValidationError(errors)
        write_serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial,
        )
        write_serializer.is_valid(raise_exception=True)
        self.perform_update(write_serializer)
        instance.refresh_from_db()
        return Response(
            UserSerializer(
                instance,
                context=self.get_serializer_context(),
            ).data
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.pk == request.user.pk:
            raise ValidationError(
                {
                    "user": [
                        "You cannot archive your own Super Admin account."
                    ]
                }
            )
        return super().destroy(request, *args, **kwargs)

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
        if setting_enabled("security.passwordPolicy"):
            try:
                validate_password(new_password, user=user)
            except DjangoValidationError as exc:
                raise ValidationError({"new_password": exc.messages}) from exc

        user.set_password(new_password)
        user.save(update_fields=["password"])
        return Response({"detail": "Password updated successfully."})
