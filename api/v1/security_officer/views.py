import mimetypes
from pathlib import PurePosixPath

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.exceptions import DomainConflict
from apps.attachments.access import (
    ProtectedAttachmentAccessDenied,
    ProtectedAttachmentNotFound,
    open_authorized_attachment,
    open_authorized_protected_file,
)
from apps.attachments.models import Attachment
from apps.security.models import Camera, Incident, IncidentAction, SafetyDocument, SecurityAlert
from apps.security.services import (
    close_incident,
    convert_alert_to_incident,
    create_manual_incident,
    dismiss_security_alert,
    record_incident_action,
    record_incident_note,
    set_incident_action_completion,
    review_security_alert,
    start_incident_investigation,
    transfer_incident,
)
from apps.users.models import Role, User
from apps.users.serializers import UserSerializer

from .permissions import (
    IsSecurityOfficerOrSuperAdmin,
    facilities_for_security_user,
    user_has_active_facility_assignment,
)
from .serializers import (
    AlertConversionInputSerializer,
    AlertDismissInputSerializer,
    AlertReviewInputSerializer,
    EvidenceReadSerializer,
    EvidenceUploadSerializer,
    IncidentActionInputSerializer,
    IncidentActionReadSerializer,
    IncidentActionCompletionSerializer,
    IncidentCloseInputSerializer,
    IncidentInvestigationInputSerializer,
    IncidentReadSerializer,
    IncidentTransferInputSerializer,
    ManualIncidentInputSerializer,
    SecurityAlertReadSerializer,
    IncidentNoteInputSerializer,
    IncidentNoteReadSerializer,
    SecurityFacilitySerializer,
    CameraSerializer,
    SafetyDocumentSerializer,
)


UUID_REGEX = (
    "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _domain_conflict(error):
    details = getattr(error, "message_dict", None) or {
        "non_field_errors": error.messages
    }
    return DomainConflict(detail=details)


def _translate_file_access(error):
    if isinstance(error, ProtectedAttachmentNotFound):
        return NotFound(str(error))
    return PermissionDenied(str(error))


def _require_assignee(assignee, facility, *, role_name, field_name="assigned_to"):
    if assignee is None:
        return
    if not user_has_active_facility_assignment(
        assignee,
        facility,
        role_name=role_name,
    ):
        role_label = dict(Role.ROLE_CHOICES)[role_name]
        raise ValidationError(
            {
                field_name: (
                    f"The assignee must be an active {role_label} assigned "
                    "to this Facility."
                )
            }
        )


class ScopedSecurityMixin:
    permission_classes = [IsSecurityOfficerOrSuperAdmin]
    lookup_value_regex = UUID_REGEX

    def visible_facilities(self):
        return facilities_for_security_user(self.request.user)


class SecurityAlertViewSet(ScopedSecurityMixin, viewsets.ReadOnlyModelViewSet):
    permission_required = "alert.view"
    serializer_class = SecurityAlertReadSerializer
    filterset_fields = [
        "facility",
        "alert_type",
        "status",
        "severity_level",
        "source",
        "location",
    ]
    search_fields = ["location", "review_notes"]
    ordering_fields = [
        "alert_type",
        "severity_level",
        "status",
        "location",
        "created_at",
        "updated_at",
    ]
    ordering = ["-created_at"]

    def get_queryset(self):
        return SecurityAlert.objects.filter(
            facility__in=self.visible_facilities()
        ).select_related(
            "facility",
            "reviewed_by",
            "created_by",
            "camera_event__camera__facility",
            "camera_event__roi",
        )

    def _service_action(self, service, **kwargs):
        alert = self.get_object()
        try:
            alert = service(
                alert_id=alert.id,
                actor=self.request.user,
                request=self.request,
                **kwargs,
            )
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(SecurityAlertReadSerializer(alert).data)

    @action(detail=True, methods=["post"], url_path="review")
    def review(self, request, pk=None):
        payload = AlertReviewInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self._service_action(
            review_security_alert,
            notes=payload.validated_data["notes"],
        )

    @action(detail=True, methods=["post"], url_path="dismiss")
    def dismiss(self, request, pk=None):
        payload = AlertDismissInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self._service_action(
            dismiss_security_alert,
            reason=payload.validated_data["reason"],
        )

    @action(detail=True, methods=["post"], url_path="convert-to-incident")
    def convert_to_incident(self, request, pk=None):
        alert = self.get_object()
        payload = AlertConversionInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        assigned_to = payload.validated_data.get("assigned_to")
        _require_assignee(
            assigned_to,
            alert.facility,
            role_name=Role.SECURITY_OFFICER,
        )
        try:
            incident = convert_alert_to_incident(
                alert_id=alert.id,
                actor=request.user,
                request=request,
                **payload.validated_data,
            )
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(
            IncidentReadSerializer(incident).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="snapshot")
    def snapshot(self, request, pk=None):
        alert = self.get_object()
        owner = alert
        field_name = "snapshot_image"
        if not alert.snapshot_image:
            try:
                owner = alert.camera_event
                field_name = "snapshot_path"
            except ObjectDoesNotExist:
                pass
        try:
            protected_file = open_authorized_protected_file(
                request.user,
                owner,
                field_name,
            )
        except (
            ProtectedAttachmentNotFound,
            ProtectedAttachmentAccessDenied,
        ) as exc:
            raise _translate_file_access(exc) from exc
        extension = PurePosixPath(protected_file.name).suffix.lower()
        filename = f"security-alert-{alert.id}{extension}"
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return FileResponse(
            protected_file,
            as_attachment=True,
            filename=filename,
            content_type=content_type,
        )


class IncidentViewSet(
    ScopedSecurityMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    permission_required = {
        "create": "incident.create",
        "close": "incident.close",
        "transfer": "incident.escalate",
        "default": "incident.update",
    }
    filterset_fields = ["facility", "status", "severity_level", "incident_type"]
    search_fields = ["incident_number", "incident_type", "description", "location"]
    ordering_fields = [
        "severity_level",
        "status",
        "closed_at",
        "created_at",
        "updated_at",
    ]
    ordering = ["-created_at"]

    def get_queryset(self):
        return Incident.objects.filter(
            facility__in=self.visible_facilities()
        ).select_related(
            "facility", "alert", "assigned_to", "closed_by", "created_by"
        )

    def get_serializer_class(self):
        if self.action == "create":
            return ManualIncidentInputSerializer
        return IncidentReadSerializer

    def create(self, request, *args, **kwargs):
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)
        facility = data.pop("facility")
        assigned_to = data.get("assigned_to")
        _require_assignee(
            assigned_to,
            facility,
            role_name=Role.SECURITY_OFFICER,
        )
        try:
            incident = create_manual_incident(
                facility_id=facility.id,
                actor=request.user,
                **data,
            )
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(
            IncidentReadSerializer(incident).data,
            status=status.HTTP_201_CREATED,
        )

    def _service_action(self, service, **kwargs):
        incident = self.get_object()
        try:
            incident = service(incident_id=incident.id, **kwargs)
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(IncidentReadSerializer(incident).data)

    @action(detail=True, methods=["post"], url_path="start-investigation")
    def start_investigation(self, request, pk=None):
        incident = self.get_object()
        payload = IncidentInvestigationInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        assigned_to = payload.validated_data.get("assigned_to")
        _require_assignee(
            assigned_to,
            incident.facility,
            role_name=Role.SECURITY_OFFICER,
        )
        return self._service_action(
            start_incident_investigation,
            assigned_to=assigned_to,
        )

    @action(detail=True, methods=["post"], url_path="transfer")
    def transfer(self, request, pk=None):
        incident = self.get_object()
        payload = IncidentTransferInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        assigned_to = payload.validated_data["assigned_to"]
        _require_assignee(
            assigned_to,
            incident.facility,
            role_name=Role.OPERATIONS_MANAGER,
        )
        return self._service_action(transfer_incident, assigned_to=assigned_to)

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        payload = IncidentCloseInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self._service_action(
            close_incident,
            actor=request.user,
            final_report=payload.validated_data["final_report"],
        )

    @action(detail=True, methods=["get", "post"], url_path="actions")
    def actions(self, request, pk=None):
        incident = self.get_object()
        if request.method == "POST":
            payload = IncidentActionInputSerializer(data=request.data)
            payload.is_valid(raise_exception=True)
            try:
                incident_action = record_incident_action(
                    incident_id=incident.id,
                    actor=request.user,
                    **payload.validated_data,
                )
            except DjangoValidationError as exc:
                raise _domain_conflict(exc) from exc
            return Response(
                IncidentActionReadSerializer(incident_action).data,
                status=status.HTTP_201_CREATED,
            )

        queryset = incident.actions.select_related("taken_by", "created_by").order_by(
            "-taken_at"
        )
        page = self.paginate_queryset(queryset)
        serializer = IncidentActionReadSerializer(
            page if page is not None else queryset,
            many=True,
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["patch"],
        url_path=rf"actions/(?P<action_id>{UUID_REGEX})/completion",
    )
    def action_completion(self, request, pk=None, action_id=None):
        incident = self.get_object()
        payload = IncidentActionCompletionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            incident_action = set_incident_action_completion(
                incident_id=incident.pk,
                action_id=action_id,
                actor=request.user,
                completed=payload.validated_data["completed"],
            )
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(IncidentActionReadSerializer(incident_action).data)

    @action(detail=True, methods=["get", "post"], url_path="notes")
    def notes(self, request, pk=None):
        incident = self.get_object()
        if request.method == "GET":
            queryset = incident.notes.select_related("author").order_by("-created_at")
            page = self.paginate_queryset(queryset)
            serializer = IncidentNoteReadSerializer(page if page is not None else queryset, many=True)
            return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)
        payload = IncidentNoteInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            note = record_incident_note(incident_id=incident.pk, actor=request.user, body=payload.validated_data["body"])
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(IncidentNoteReadSerializer(note).data, status=status.HTTP_201_CREATED)

    def _evidence(self, request, *, entity_type, entity_id):
        if request.method == "POST":
            payload = EvidenceUploadSerializer(
                data=request.data,
                context={
                    "request": request,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                },
            )
            payload.is_valid(raise_exception=True)
            attachment = payload.save()
            return Response(
                EvidenceReadSerializer(
                    attachment,
                    context={"request": request},
                ).data,
                status=status.HTTP_201_CREATED,
            )

        attachments = Attachment.objects.filter(
            entity_type=entity_type,
            entity_id=entity_id,
        ).select_related("created_by")
        page = self.paginate_queryset(attachments)
        serializer = EvidenceReadSerializer(
            page if page is not None else attachments,
            many=True,
            context={"request": request},
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["get", "post"], url_path="evidence")
    def evidence(self, request, pk=None):
        incident = self.get_object()
        return self._evidence(
            request,
            entity_type="incident",
            entity_id=incident.id,
        )

    @action(
        detail=True,
        methods=["get", "post"],
        url_path=rf"actions/(?P<action_id>{UUID_REGEX})/evidence",
    )
    def action_evidence(self, request, pk=None, action_id=None):
        incident = self.get_object()
        incident_action = get_object_or_404(
            IncidentAction.objects,
            pk=action_id,
            incident=incident,
        )
        return self._evidence(
            request,
            entity_type="incident_action",
            entity_id=incident_action.id,
        )


class SecurityEvidenceViewSet(ScopedSecurityMixin, viewsets.GenericViewSet):
    permission_required = "incident.update"
    serializer_class = EvidenceReadSerializer
    @property
    def queryset(self):
        facilities = self.visible_facilities()
        incident_ids = Incident.objects.filter(facility__in=facilities).values("id")
        action_ids = IncidentAction.objects.filter(
            incident__facility__in=facilities
        ).values("id")
        return Attachment.objects.filter(
            Q(entity_type="incident", entity_id__in=incident_ids)
            | Q(entity_type="incident_action", entity_id__in=action_ids)
        ).select_related("created_by")

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        attachment = self.get_object()
        try:
            protected_file = open_authorized_attachment(request.user, attachment)
        except (
            ProtectedAttachmentNotFound,
            ProtectedAttachmentAccessDenied,
        ) as exc:
            raise _translate_file_access(exc) from exc
        return FileResponse(
            protected_file,
            as_attachment=True,
            filename=attachment.original_file_name,
            content_type=attachment.mime_type,
        )


class SecurityFacilityViewSet(ScopedSecurityMixin, viewsets.ReadOnlyModelViewSet):
    permission_required = "alert.view"
    serializer_class = SecurityFacilitySerializer
    filterset_fields = ["status", "type"]
    search_fields = ["name", "location"]
    ordering_fields = ["name", "status", "created_at"]

    def get_queryset(self):
        return self.visible_facilities().select_related("created_from_project")


class CameraViewSet(ScopedSecurityMixin, viewsets.ReadOnlyModelViewSet):
    permission_required = "alert.view"
    serializer_class = CameraSerializer
    filterset_fields = ["facility", "status", "zone"]
    search_fields = ["code", "name", "zone"]
    ordering_fields = ["code", "status", "last_seen_at", "created_at"]

    def get_queryset(self):
        return Camera.objects.filter(facility__in=self.visible_facilities()).select_related("facility", "asset")


class SafetyDocumentViewSet(ScopedSecurityMixin, viewsets.ModelViewSet):
    permission_required = "incident.update"
    serializer_class = SafetyDocumentSerializer
    filterset_fields = ["facility", "category"]
    search_fields = ["title", "original_file_name"]
    ordering_fields = ["title", "created_at"]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return SafetyDocument.objects.filter(facility__in=self.visible_facilities()).select_related("facility", "created_by")

    def perform_create(self, serializer):
        validated_data = dict(serializer.validated_data)
        facility = validated_data.pop("facility")
        if not self.visible_facilities().filter(pk=facility.pk).exists():
            raise PermissionDenied("You cannot add documents to this facility.")
        document = SafetyDocument(
            facility=facility,
            created_by=self.request.user,
            **validated_data,
        )
        document.save()
        serializer.instance = document

    def perform_destroy(self, instance):
        instance.soft_delete()

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        document = self.get_object()
        return FileResponse(
            document.file.open("rb"),
            as_attachment=True,
            filename=document.original_file_name,
            content_type=document.mime_type,
        )


class SecurityAssigneeView(APIView):
    permission_required = "incident.update"
    permission_classes = [IsSecurityOfficerOrSuperAdmin]

    @extend_schema(responses=UserSerializer(many=True))
    def get(self, request):
        role_name = request.query_params.get("role", Role.SECURITY_OFFICER)
        if role_name not in {Role.SECURITY_OFFICER, Role.OPERATIONS_MANAGER}:
            raise ValidationError({"role": "Unsupported assignee role."})
        users = User.objects.filter(status=User.STATUS_ACTIVE, role__name=role_name)
        if request.user.role.name != Role.SUPER_ADMIN:
            users = users.filter(facility_assignments__facility__in=facilities_for_security_user(request.user), facility_assignments__is_active=True)
        return Response(UserSerializer(users.select_related("role").distinct().order_by("full_name"), many=True).data)
