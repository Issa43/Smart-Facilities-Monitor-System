from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from api.v1.exceptions import DomainConflict
from apps.common.permissions import IsSuperAdmin
from apps.projects.models import Project, ProjectAssignment
from apps.projects.services import (
    calculate_project_progress,
    complete_project,
    convert_project_to_facility,
    start_project,
)
from apps.security.machine_credentials import (
    add_ai_ingestion_camera_scope,
    create_ai_ingestion_credential,
    remove_ai_ingestion_camera_scope,
    revoke_ai_ingestion_credential,
    rotate_ai_ingestion_credential,
)
from apps.security.models import AIIngestionCredential, Camera

from .serializers import (
    AIIngestionCameraScopeInputSerializer,
    AIIngestionCredentialCreateSerializer,
    AIIngestionCredentialReadSerializer,
    CompleteProjectSerializer,
    FacilityConversionSerializer,
    ProjectAssignmentSerializer,
    ProjectReadSerializer,
    ProjectWriteSerializer,
)


def _domain_conflict(error):
    details = getattr(error, "message_dict", None) or {
        "non_field_errors": error.messages
    }
    return DomainConflict(detail=details)


class AIIngestionCredentialViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Super Admin-only lifecycle management for scoped machine credentials."""

    permission_classes = [IsSuperAdmin]
    queryset = AIIngestionCredential.all_objects.select_related(
        "principal", "revoked_by", "created_by"
    )
    serializer_class = AIIngestionCredentialReadSerializer
    filterset_fields = ["is_active", "key_id"]
    search_fields = ["name", "key_id"]
    ordering_fields = ["name", "created_at", "expires_at", "last_used_at"]
    ordering = ["-created_at"]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def create(self, request, *args, **kwargs):
        payload = AIIngestionCredentialCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            credential, secret = create_ai_ingestion_credential(
                actor=request.user,
                request=request,
                **payload.validated_data,
            )
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        response = AIIngestionCredentialReadSerializer(
            credential,
            context=self.get_serializer_context(),
        ).data
        response["secret"] = secret
        response["authorization_scheme"] = "AIKey"
        return Response(response, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def rotate(self, request, pk=None):
        try:
            credential, secret = rotate_ai_ingestion_credential(
                credential_id=self.get_object().pk,
                actor=request.user,
                request=request,
            )
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        response = self.get_serializer(credential).data
        response["secret"] = secret
        response["authorization_scheme"] = "AIKey"
        return Response(response)

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        try:
            credential = revoke_ai_ingestion_credential(
                credential_id=self.get_object().pk,
                actor=request.user,
                request=request,
            )
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(self.get_serializer(credential).data)

    @action(detail=True, methods=["post"], url_path="scopes")
    def add_scope(self, request, pk=None):
        payload = AIIngestionCameraScopeInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            add_ai_ingestion_camera_scope(
                credential=self.get_object(),
                camera=payload.validated_data["camera"],
                actor=request.user,
                request=request,
            )
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        credential = self.get_queryset().get(pk=self.kwargs["pk"])
        return Response(self.get_serializer(credential).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"scopes/(?P<camera_id>[0-9a-fA-F-]{36})",
    )
    def remove_scope(self, request, pk=None, camera_id=None):
        camera = get_object_or_404(Camera.objects, pk=camera_id)
        try:
            remove_ai_ingestion_camera_scope(
                credential=self.get_object(),
                camera=camera,
                actor=request.user,
                request=request,
            )
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        credential = self.get_queryset().get(pk=self.kwargs["pk"])
        return Response(self.get_serializer(credential).data)


class ProjectViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsSuperAdmin]
    queryset = Project.objects.select_related("facility", "created_by").prefetch_related(
        "assignments__user", "phases"
    )
    filterset_fields = ["status", "facility_type", "facility"]
    search_fields = ["name", "description", "location"]
    ordering_fields = [
        "name",
        "start_date",
        "expected_completion_date",
        "created_at",
        "updated_at",
    ]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return ProjectWriteSerializer
        return ProjectReadSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = serializer.save()
        return Response(
            ProjectReadSerializer(project, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        project = self.get_object()
        serializer = self.get_serializer(project, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        project = serializer.save()
        return Response(
            ProjectReadSerializer(project, context=self.get_serializer_context()).data
        )

    def destroy(self, request, *args, **kwargs):
        project = self.get_object()
        if project.status != Project.Status.PLANNING:
            raise DomainConflict("Only planning projects can be archived.")
        project.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"])
    def overview(self, request):
        projects = list(Project.objects.all())
        status_counts = {
            row["status"]: row["total"]
            for row in Project.objects.values("status").annotate(total=Count("id"))
        }
        progress_values = [calculate_project_progress(project) for project in projects]
        average_progress = (
            sum(progress_values, Decimal("0.00")) / len(progress_values)
            if progress_values
            else Decimal("0.00")
        )
        return Response(
            {
                "total_projects": len(projects),
                "status_counts": {
                    value: status_counts.get(value, 0) for value in Project.Status.values
                },
                "average_progress_percentage": average_progress.quantize(
                    Decimal("0.01")
                ),
            }
        )

    @action(detail=False, methods=["get"])
    def monitoring(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = ProjectReadSerializer(
            page if page is not None else queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="start")
    def start(self, request, pk=None):
        self.get_object()
        try:
            project = start_project(project_id=pk)
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(ProjectReadSerializer(project).data)

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        self.get_object()
        payload = CompleteProjectSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            project = complete_project(
                project_id=pk,
                actual_completion_date=payload.validated_data[
                    "actual_completion_date"
                ],
            )
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(ProjectReadSerializer(project).data)

    @action(detail=True, methods=["post"], url_path="convert-to-facility")
    def convert_to_facility(self, request, pk=None):
        self.get_object()
        try:
            facility = convert_project_to_facility(
                project_id=pk,
                actor=request.user,
            )
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(
            FacilityConversionSerializer(facility).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get", "post"], url_path="assignments")
    def assignments(self, request, pk=None):
        project = self.get_object()
        if request.method == "GET":
            assignments = ProjectAssignment.objects.filter(project=project).select_related(
                "user", "created_by"
            )
            return Response(ProjectAssignmentSerializer(assignments, many=True).data)

        serializer = ProjectAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        role_type = serializer.validated_data["role_type"]

        with transaction.atomic():
            existing = ProjectAssignment.all_objects.select_for_update().filter(
                project=project,
                user=user,
                role_type=role_type,
            ).first()
            if existing and existing.is_active:
                raise DomainConflict("This project assignment already exists.")
            if existing:
                existing.is_active = True
                try:
                    existing.full_clean()
                except DjangoValidationError as exc:
                    raise _domain_conflict(exc) from exc
                existing.save(update_fields=["is_active", "updated_at"])
                assignment = existing
                response_status = status.HTTP_200_OK
            else:
                assignment = ProjectAssignment(
                    project=project,
                    user=user,
                    role_type=role_type,
                    created_by=request.user,
                )
                try:
                    assignment.full_clean()
                    assignment.save()
                except DjangoValidationError as exc:
                    raise _domain_conflict(exc) from exc
                except IntegrityError as exc:
                    raise DomainConflict(
                        "The assignment changed concurrently; retry the request."
                    ) from exc
                response_status = status.HTTP_201_CREATED

        return Response(
            ProjectAssignmentSerializer(assignment).data,
            status=response_status,
        )

    @extend_schema(
        parameters=[OpenApiParameter("assignment_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
        responses={204: None},
    )
    @action(
        detail=True,
        methods=["delete"],
        url_path=r"assignments/(?P<assignment_id>[^/.]+)",
    )
    def assignment_detail(self, request, pk=None, assignment_id=None):
        project = self.get_object()
        assignment = get_object_or_404(
            ProjectAssignment.objects,
            pk=assignment_id,
            project=project,
        )
        assignment.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
