from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import FileResponse
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from api.v1.exceptions import DomainConflict
from apps.construction.models import DailyReport, QualityInspection, SitePhoto
from apps.materials.models import Material, MaterialConsumptionRecord, MaterialRequest
from apps.materials.services import approve_material_request, consume_material, fulfill_material_request, reject_material_request, review_material_request
from apps.projects.models import Project, ProjectDocument, ProjectPhase
from apps.projects.services import (
    approve_phase,
    calculate_project_progress,
    complete_project,
    record_phase_progress,
    reject_phase,
    request_phase_modification,
)
from apps.users.models import Role
from apps.notifications.services import setting_enabled

from .permissions import IsConstructionManagerOrSuperAdmin
from .serializers import (
    PhaseProgressInputSerializer,
    PhaseProgressLogSerializer,
    PhaseReviewInputSerializer,
    PhaseReviewLogSerializer,
    ProjectPhaseReadSerializer,
    ProjectPhaseWriteSerializer,
    ProjectReadSerializer,
    MaterialSerializer,
    MaterialConsumptionInputSerializer,
    MaterialConsumptionSerializer,
    MaterialRequestSerializer,
    DailyReportSerializer,
    QualityInspectionSerializer,
    ProjectDocumentSerializer,
    SitePhotoSerializer,
)


def _domain_conflict(error):
    details = getattr(error, "message_dict", None) or {
        "non_field_errors": error.messages
    }
    return DomainConflict(detail=details)


def projects_for_user(user):
    queryset = Project.objects.all()
    if not user or not user.is_authenticated or not getattr(user, "role_id", None):
        return queryset.none()
    if user.role.name != Role.SUPER_ADMIN:
        queryset = queryset.filter(assignments__user=user, assignments__is_active=True)
    return queryset.distinct()


class ScopedProjectViewSet(viewsets.ReadOnlyModelViewSet):
    permission_required = {
        "complete": "project.close",
        "completion_check": "project.close",
        "default": "project.view",
    }
    permission_classes = [IsConstructionManagerOrSuperAdmin]
    serializer_class = ProjectReadSerializer
    filterset_fields = ["status", "facility_type"]
    search_fields = ["name", "description", "location"]
    ordering_fields = ["name", "start_date", "expected_completion_date", "created_at", "updated_at"]

    def get_queryset(self):
        return projects_for_user(self.request.user).select_related("facility", "created_by").prefetch_related("assignments", "phases")

    @action(detail=True, methods=["get"], url_path="image")
    def image(self, request, pk=None):
        project = self.get_object()
        if not project.image:
            from rest_framework.exceptions import NotFound
            raise NotFound("This project has no image.")
        return FileResponse(project.image.open("rb"), content_type="application/octet-stream")

    @action(detail=True, methods=["get"], url_path="completion-check")
    def completion_check(self, request, pk=None):
        project = self.get_object()
        phases = ProjectPhase.objects.filter(project=project)
        requests = MaterialRequest.objects.filter(project=project)
        incomplete = phases.exclude(status=ProjectPhase.Status.COMPLETED).count()
        rejected = phases.filter(status=ProjectPhase.Status.REJECTED).count()
        open_requests = requests.filter(
            status__in=[
                MaterialRequest.Status.SUBMITTED,
                MaterialRequest.Status.REVIEWED,
                MaterialRequest.Status.APPROVED,
            ]
        ).count()
        completion_rules_enforced = setting_enabled("workflow.blockCompletion")
        return Response(
            {
                "can_complete": bool(
                    not completion_rules_enforced
                    or (phases.exists() and not incomplete and not rejected and not open_requests)
                ),
                "completion_rules_enforced": completion_rules_enforced,
                "all_stages_completed": bool(phases.exists() and not incomplete),
                "no_rejected_stages": rejected == 0,
                "no_open_material_requests": open_requests == 0,
                "incomplete_stage_count": incomplete,
                "rejected_stage_count": rejected,
                "open_request_count": open_requests,
            }
        )

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        project = self.get_object()
        actual_completion_date = request.data.get("actual_completion_date")
        from rest_framework.serializers import DateField

        date_field = DateField()
        completion_date = date_field.run_validation(actual_completion_date)
        try:
            project = complete_project(
                project_id=project.pk,
                actual_completion_date=completion_date,
            )
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(ProjectReadSerializer(project).data)


class ProjectScopedModelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsConstructionManagerOrSuperAdmin]
    project_field = "project"

    def scoped_projects(self):
        return projects_for_user(self.request.user)

    def project_from_request(self, serializer):
        project_id = self.request.data.get("project") or self.request.data.get("project_id")
        if not project_id and getattr(serializer, "instance", None):
            return getattr(serializer.instance, self.project_field)
        return get_object_or_404(self.scoped_projects(), pk=project_id)

    def perform_destroy(self, instance):
        instance.soft_delete()


class FlatProjectPhaseViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsConstructionManagerOrSuperAdmin]
    permission_required = "project.view"
    serializer_class = ProjectPhaseReadSerializer
    filterset_fields = ["project", "status", "priority"]
    search_fields = ["name", "description"]
    ordering_fields = ["sequence_number", "start_date", "expected_completion_date", "current_progress"]
    ordering = ["project", "sequence_number"]

    def get_queryset(self):
        return ProjectPhase.objects.filter(
            project__in=projects_for_user(self.request.user)
        ).select_related("project", "approved_by", "created_by")


class MaterialViewSet(ProjectScopedModelViewSet):
    permission_required = {"list": "material.stock", "retrieve": "material.stock", "default": "material.manage"}
    serializer_class = MaterialSerializer
    filterset_fields = ["project", "unit"]
    search_fields = ["name"]
    ordering_fields = ["name", "quantity_remaining", "created_at"]

    def get_queryset(self):
        return Material.objects.filter(project__in=self.scoped_projects()).select_related("project")

    def perform_create(self, serializer):
        project = self.project_from_request(serializer)
        material = Material(project=project, created_by=self.request.user, **serializer.validated_data)
        material.full_clean(); material.save()
        serializer.instance = material

    @action(detail=True, methods=["get", "post"], url_path="consumption")
    def consumption(self, request, pk=None):
        material = self.get_object()
        if request.method == "GET":
            queryset = MaterialConsumptionRecord.objects.filter(
                material=material
            ).select_related("phase", "created_by").order_by("-usage_date", "-created_at")
            page = self.paginate_queryset(queryset)
            serializer = MaterialConsumptionSerializer(
                page if page is not None else queryset,
                many=True,
            )
            return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)
        payload = MaterialConsumptionInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        phase = payload.validated_data.get("phase")
        if phase and phase.project_id != material.project_id:
            raise ValidationError({"phase": "The phase must belong to the material project."})
        try:
            record = consume_material(
                material_id=material.pk,
                quantity=payload.validated_data["quantity"],
                usage_date=payload.validated_data.get("usage_date"),
                phase=phase,
                actor=request.user,
            )
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(
            MaterialConsumptionSerializer(record).data,
            status=status.HTTP_201_CREATED,
        )


class MaterialRequestViewSet(ProjectScopedModelViewSet):
    permission_required = "material.request"
    serializer_class = MaterialRequestSerializer
    filterset_fields = ["project", "material", "priority", "status"]
    search_fields = ["material__name", "reason"]
    ordering_fields = ["priority", "status", "created_at"]

    def get_queryset(self):
        return MaterialRequest.objects.filter(project__in=self.scoped_projects()).select_related("project", "material", "created_by")

    def perform_create(self, serializer):
        project = self.project_from_request(serializer)
        data = dict(serializer.validated_data)
        submitted_material = data.pop("material")
        material = get_object_or_404(Material.objects.filter(project=project), pk=submitted_material.pk)
        request_obj = MaterialRequest(project=project, material=material, created_by=self.request.user, **data)
        request_obj.full_clean(); request_obj.save(); serializer.instance = request_obj

    def _transition(self, service):
        obj = self.get_object()
        try:
            if service is approve_material_request:
                obj = service(obj.pk, actor=self.request.user)
            else:
                obj = service(obj.pk)
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None): return self._transition(review_material_request)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None): return self._transition(approve_material_request)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None): return self._transition(reject_material_request)
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None): return self._transition(fulfill_material_request)


class DailyReportViewSet(ProjectScopedModelViewSet):
    permission_required = "project.edit"
    serializer_class = DailyReportSerializer
    filterset_fields = {"project": ["exact"], "phase": ["exact"], "report_date": ["exact", "gte", "lte"]}
    search_fields = ["title", "report_content", "issues"]
    ordering_fields = ["report_date", "progress_percentage", "created_at"]

    def get_queryset(self):
        return DailyReport.objects.filter(project__in=self.scoped_projects()).select_related("project", "phase", "created_by")

    def perform_create(self, serializer):
        project = self.project_from_request(serializer)
        report = DailyReport(project=project, created_by=self.request.user, report_date=serializer.validated_data.pop("report_date", timezone.localdate()), **serializer.validated_data)
        report.full_clean(); report.save(); serializer.instance = report


class QualityInspectionViewSet(ProjectScopedModelViewSet):
    permission_required = "stage.approve"
    serializer_class = QualityInspectionSerializer
    filterset_fields = ["project", "phase", "result"]
    search_fields = ["title", "notes"]
    ordering_fields = ["inspected_at", "score", "created_at"]

    def get_queryset(self):
        return QualityInspection.objects.filter(project__in=self.scoped_projects()).select_related("project", "phase", "inspector")

    def perform_create(self, serializer):
        project = self.project_from_request(serializer)
        inspection = QualityInspection(project=project, inspector=self.request.user, created_by=self.request.user, inspected_at=serializer.validated_data.pop("inspected_at", timezone.now()), **serializer.validated_data)
        inspection.full_clean(); inspection.save(); serializer.instance = inspection


class ProjectDocumentViewSet(ProjectScopedModelViewSet):
    permission_required = "project.edit"
    serializer_class = ProjectDocumentSerializer
    filterset_fields = ["project", "document_type"]
    search_fields = ["title", "original_file_name"]
    ordering_fields = ["title", "created_at"]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return ProjectDocument.objects.filter(project__in=self.scoped_projects()).select_related("project", "created_by")

    def perform_create(self, serializer):
        project = self.project_from_request(serializer)
        document = ProjectDocument(project=project, created_by=self.request.user, **serializer.validated_data)
        document.save(); serializer.instance = document

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        document = self.get_object()
        return FileResponse(document.file.open("rb"), as_attachment=True, filename=document.original_file_name, content_type=document.mime_type)


class SitePhotoViewSet(ProjectScopedModelViewSet):
    permission_required = "project.edit"
    serializer_class = SitePhotoSerializer
    filterset_fields = ["project", "phase"]
    search_fields = ["caption"]
    ordering_fields = ["captured_at", "created_at"]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return SitePhoto.objects.filter(project__in=self.scoped_projects()).select_related("project", "phase", "created_by")

    def perform_create(self, serializer):
        project = self.project_from_request(serializer)
        photo = SitePhoto(project=project, created_by=self.request.user, captured_at=serializer.validated_data.pop("captured_at", timezone.now()), **serializer.validated_data)
        photo.save(); serializer.instance = photo

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        photo = self.get_object()
        return FileResponse(photo.image.open("rb"), filename=photo.original_file_name, content_type=photo.mime_type)


class ProjectPhaseViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    permission_required = {
        "list": "project.view", "retrieve": "project.view",
        "create": "stage.create", "update": "stage.edit",
        "partial_update": "stage.edit", "progress": "stage.progress",
        "destroy": "stage.delete",
        "approve": "stage.approve", "reject": "stage.approve",
        "request_modification": "stage.approve", "default": "project.view",
    }
    """Manage phases within the requester's assigned project scope."""

    permission_classes = [IsConstructionManagerOrSuperAdmin]
    lookup_value_regex = (
        "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    )
    filterset_fields = ["status", "priority"]
    search_fields = ["name", "description"]
    ordering_fields = [
        "sequence_number",
        "start_date",
        "expected_completion_date",
        "current_progress",
        "created_at",
        "updated_at",
    ]
    ordering = ["sequence_number"]

    def _get_project(self):
        if not hasattr(self, "_scoped_project"):
            projects = Project.objects.all()
            user = self.request.user
            if user.role.name != Role.SUPER_ADMIN:
                projects = projects.filter(
                    assignments__user=user,
                    assignments__is_active=True,
                ).distinct()
            self._scoped_project = get_object_or_404(
                projects,
                pk=self.kwargs["project_id"],
            )
        return self._scoped_project

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ProjectPhase.objects.none()
        return (
            ProjectPhase.objects.filter(project=self._get_project())
            .select_related("project", "approved_by", "created_by")
            .order_by("sequence_number")
        )

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return ProjectPhaseWriteSerializer
        return ProjectPhaseReadSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action in {"create", "update", "partial_update"}:
            context["project"] = self._get_project()
        return context

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                phase = serializer.save()
        except IntegrityError as exc:
            raise DomainConflict(
                "The phase sequence changed concurrently; retry the request."
            ) from exc
        return Response(
            ProjectPhaseReadSerializer(phase).data,
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        phase = self.get_object()
        if phase.status != ProjectPhase.Status.NOT_STARTED or phase.current_progress != 0:
            raise DomainConflict("Only an unstarted phase at 0% can be deleted.")
        phase.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        phase = self.get_object()
        serializer = self.get_serializer(phase, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                phase = serializer.save()
        except IntegrityError as exc:
            raise DomainConflict(
                "The phase sequence changed concurrently; retry the request."
            ) from exc
        return Response(ProjectPhaseReadSerializer(phase).data)

    @action(detail=False, methods=["get"], url_path="monitoring")
    def monitoring(self, request, project_id=None):
        project = self._get_project()
        phases = self.get_queryset()
        status_counts = {
            row["status"]: row["total"]
            for row in phases.values("status").annotate(total=Count("id"))
        }
        return Response(
            {
                "project_id": project.id,
                "project_status": project.status,
                "project_progress_percentage": calculate_project_progress(project),
                "total_phases": phases.count(),
                "status_counts": {
                    value: status_counts.get(value, 0)
                    for value in ProjectPhase.Status.values
                },
            }
        )

    @action(detail=True, methods=["post"], url_path="progress")
    def progress(self, request, project_id=None, pk=None):
        phase = self.get_object()
        payload = PhaseProgressInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            progress_log = record_phase_progress(
                phase_id=phase.id,
                actor=request.user,
                **payload.validated_data,
            )
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(
            PhaseProgressLogSerializer(progress_log).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="progress-history")
    def progress_history(self, request, project_id=None, pk=None):
        phase = self.get_object()
        queryset = phase.progress_logs.select_related("created_by").order_by(
            "-created_at"
        )
        page = self.paginate_queryset(queryset)
        serializer = PhaseProgressLogSerializer(
            page if page is not None else queryset,
            many=True,
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="review-history")
    def review_history(self, request, project_id=None, pk=None):
        phase = self.get_object()
        queryset = phase.review_logs.select_related("created_by").order_by(
            "-created_at"
        )
        page = self.paginate_queryset(queryset)
        serializer = PhaseReviewLogSerializer(
            page if page is not None else queryset,
            many=True,
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, project_id=None, pk=None):
        phase = self.get_object()
        try:
            review = approve_phase(phase_id=phase.id, actor=request.user)
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(
            PhaseReviewLogSerializer(review).data,
            status=status.HTTP_201_CREATED,
        )

    def _reject_with(self, request, service):
        phase = self.get_object()
        payload = PhaseReviewInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            review = service(
                phase_id=phase.id,
                actor=request.user,
                reason=payload.validated_data["reason"],
            )
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(
            PhaseReviewLogSerializer(review).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, project_id=None, pk=None):
        return self._reject_with(request, reject_phase)

    @action(detail=True, methods=["post"], url_path="request-modification")
    def request_modification(self, request, project_id=None, pk=None):
        return self._reject_with(request, request_phase_modification)
