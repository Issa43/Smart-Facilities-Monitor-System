from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from api.v1.exceptions import DomainConflict
from apps.attachments.access import (
    ProtectedAttachmentAccessDenied,
    ProtectedAttachmentNotFound,
    open_authorized_protected_file,
)
from apps.reports.models import Report, ReportTemplate
from apps.reports.services import (
    create_report_request,
    create_report_template,
    requeue_failed_report,
    update_report_template,
)
from apps.reports.tasks import generate_report_task
from apps.users.models import Role

from .permissions import (
    CanManageReportTemplates,
    CanUseReports,
    has_report_object_scope,
    report_modules_for_user,
)
from .serializers import (
    ReportRequestCreateSerializer,
    ReportRequestReadSerializer,
    ReportTemplateCreateSerializer,
    ReportTemplateReadSerializer,
    ReportTemplateUpdateSerializer,
    raise_drf_validation,
)


UUID_REGEX = (
    "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


class ReportTemplateViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    lookup_value_regex = UUID_REGEX
    filterset_fields = ["module", "format"]
    search_fields = ["name"]
    ordering_fields = ["name", "module", "format", "created_at", "updated_at"]
    ordering = ["name"]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update"}:
            return [CanManageReportTemplates()]
        return [CanUseReports()]

    def get_queryset(self):
        return ReportTemplate.objects.filter(
            module__in=report_modules_for_user(self.request.user)
        ).select_related("created_by")

    def get_serializer_class(self):
        if self.action == "create":
            return ReportTemplateCreateSerializer
        if self.action in {"update", "partial_update"}:
            return ReportTemplateUpdateSerializer
        return ReportTemplateReadSerializer

    def create(self, request, *args, **kwargs):
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            template = create_report_template(
                name=payload.validated_data["name"],
                module=payload.validated_data["module"],
                report_format=payload.validated_data["format"],
                configuration=payload.validated_data["configuration"],
                actor=request.user,
            )
        except DjangoValidationError as exc:
            raise_drf_validation(exc)
        return Response(
            ReportTemplateReadSerializer(template).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        template = self.get_object()
        payload = self.get_serializer(data=request.data, partial=partial)
        payload.is_valid(raise_exception=True)
        try:
            template = update_report_template(
                template_id=template.pk,
                name=payload.validated_data.get("name", template.name),
                configuration=payload.validated_data.get(
                    "configuration",
                    template.configuration,
                ),
            )
        except DjangoValidationError as exc:
            raise_drf_validation(exc)
        return Response(ReportTemplateReadSerializer(template).data)


class ReportRequestViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [CanUseReports]
    lookup_value_regex = UUID_REGEX
    filterset_fields = {
        "module": ["exact"],
        "format": ["exact"],
        "status": ["exact"],
        "type": ["exact"],
        "created_at": ["date", "gte", "lte"],
    }
    search_fields = ["type"]
    ordering_fields = ["type", "module", "format", "status", "created_at", "updated_at"]
    ordering = ["-created_at"]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Report.objects.none()
        queryset = Report.objects.filter(
            module__in=report_modules_for_user(self.request.user)
        )
        if self.request.user.role.name != Role.SUPER_ADMIN:
            queryset = queryset.filter(created_by=self.request.user)
        return queryset.select_related("created_by")

    def get_serializer_class(self):
        if self.action == "create":
            return ReportRequestCreateSerializer
        return ReportRequestReadSerializer

    def create(self, request, *args, **kwargs):
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)
        template = data.pop("template", None)
        if data["module"] not in report_modules_for_user(request.user):
            raise PermissionDenied("This role cannot generate that report module.")
        scope_parameters = dict(
            (template.configuration.get("default_parameters", {}) if template else {})
        )
        scope_parameters.update(data["parameters"])
        if not has_report_object_scope(
            request.user,
            data["module"],
            scope_parameters,
        ):
            raise PermissionDenied(
                "The report must be scoped to an assigned Project or Facility."
            )
        try:
            report = create_report_request(
                report_type=data["type"],
                module=data["module"],
                report_format=data["format"],
                parameters=data["parameters"],
                actor=request.user,
                template_id=template.pk if template else None,
            )
        except DjangoValidationError as exc:
            raise_drf_validation(exc)
        generate_report_task.delay(str(report.pk))
        return Response(
            ReportRequestReadSerializer(report, context={"request": request}).data,
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"], url_path="retry")
    def retry(self, request, pk=None):
        report = self.get_object()
        try:
            report = requeue_failed_report(report_id=report.pk)
        except DjangoValidationError as exc:
            raise_drf_validation(exc)
        generate_report_task.delay(str(report.pk))
        return Response(
            ReportRequestReadSerializer(report, context={"request": request}).data,
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        report = self.get_object()
        if report.status != Report.Status.COMPLETED or not report.file_path:
            raise DomainConflict("Only completed reports can be downloaded.")
        try:
            protected_file = open_authorized_protected_file(
                request.user,
                report,
                "file_path",
            )
        except ProtectedAttachmentNotFound as exc:
            raise NotFound(str(exc)) from exc
        except ProtectedAttachmentAccessDenied as exc:
            raise PermissionDenied(str(exc)) from exc
        extension = ".pdf" if report.format == Report.Format.PDF else ".xlsx"
        filename = f"report-{report.id}{extension}"
        content_type = (
            "application/pdf"
            if report.format == Report.Format.PDF
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        return FileResponse(
            protected_file,
            as_attachment=True,
            filename=filename,
            content_type=content_type,
        )
