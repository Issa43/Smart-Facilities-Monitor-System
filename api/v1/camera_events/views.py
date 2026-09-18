import mimetypes
from pathlib import PurePosixPath

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from drf_spectacular.utils import extend_schema

from api.v1.exceptions import DomainConflict
from api.v1.security_officer.permissions import (
    IsSecurityOfficerOrSuperAdmin,
    facilities_for_security_user,
)
from apps.attachments.access import (
    ProtectedAttachmentAccessDenied,
    ProtectedAttachmentNotFound,
    open_authorized_protected_file,
)
from apps.security.authentication import AIIngestionAuthentication
from apps.security.camera_events import (
    CameraEventConflict,
    create_camera_event,
    update_camera_event,
)
from apps.security.models import CameraEvent
from apps.security.permissions import IsAIIngestionMachine
from apps.security.throttling import AIIngestionRateThrottle

from .serializers import (
    CameraEventCreateSerializer,
    CameraEventPatchSerializer,
    CameraEventReadSerializer,
)
from .openapi import CAMERA_EVENT_CREATE_REQUEST


UUID_REGEX = (
    "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _input_validation(error):
    details = getattr(error, "message_dict", None) or {
        "non_field_errors": error.messages
    }
    return ValidationError(detail=details)


class CameraEventViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    http_method_names = ["get", "post", "patch", "head", "options"]
    lookup_value_regex = UUID_REGEX
    filterset_fields = {
        "camera": ["exact"],
        "event_type": ["exact"],
        "detected_at": ["gte", "lte"],
        "plate_number": ["exact"],
        "authorized": ["exact"],
        "tamper_type": ["exact"],
    }
    ordering_fields = ["detected_at", "created_at", "updated_at"]
    ordering = ["-detected_at"]

    def initialize_request(self, request, *args, **kwargs):
        self._requested_method = request.method
        return super().initialize_request(request, *args, **kwargs)

    def get_authenticators(self):
        if getattr(self, "_requested_method", None) in {"POST", "PATCH"}:
            return [AIIngestionAuthentication()]
        return [JWTAuthentication()]

    def get_permissions(self):
        if self.request.method in {"POST", "PATCH"}:
            return [IsAIIngestionMachine()]
        return [IsSecurityOfficerOrSuperAdmin()]

    def get_throttles(self):
        if self.request.method in {"POST", "PATCH"}:
            return [AIIngestionRateThrottle()]
        return super().get_throttles()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CameraEventCreateSerializer
        if self.request.method == "PATCH":
            return CameraEventPatchSerializer
        return CameraEventReadSerializer

    def get_queryset(self):
        queryset = CameraEvent.objects.select_related(
            "camera__facility",
            "ingestion_credential__principal",
            "roi",
            "security_alert",
        )
        if self.request.method == "PATCH":
            credential = getattr(self.request, "auth", None)
            return queryset.filter(ingestion_credential=credential)
        return queryset.filter(
            camera__facility__in=facilities_for_security_user(self.request.user)
        )

    @extend_schema(
        request=CAMERA_EVENT_CREATE_REQUEST,
        responses={200: CameraEventReadSerializer, 201: CameraEventReadSerializer},
    )
    def create(self, request, *args, **kwargs):
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        values = dict(payload.validated_data)
        camera_id = values.pop("camera")
        source_event_id = values.pop("source_event_id")
        try:
            event, created = create_camera_event(
                credential=request.auth,
                source_event_id=source_event_id,
                camera_id=camera_id,
                data=values,
            )
        except CameraEventConflict as exc:
            details = getattr(exc, "message_dict", None) or exc.messages
            raise DomainConflict(detail=details) from exc
        except DjangoValidationError as exc:
            raise _input_validation(exc) from exc
        event.refresh_from_db()
        return Response(
            CameraEventReadSerializer(event, context={"request": request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(
        request=CameraEventPatchSerializer,
        responses=CameraEventReadSerializer,
    )
    def partial_update(self, request, *args, **kwargs):
        event = self.get_object()
        payload = self.get_serializer(
            data=request.data,
            partial=True,
            context={"event": event},
        )
        payload.is_valid(raise_exception=True)
        try:
            event = update_camera_event(
                event_id=event.pk,
                credential=request.auth,
                changes=dict(payload.validated_data),
            )
        except DjangoValidationError as exc:
            raise _input_validation(exc) from exc
        return Response(
            CameraEventReadSerializer(event, context={"request": request}).data
        )

    def update(self, request, *args, **kwargs):
        raise ValidationError("Only partial updates are supported.")

    @action(detail=True, methods=["get"], url_path="snapshot")
    def snapshot(self, request, pk=None):
        event = self.get_object()
        try:
            protected_file = open_authorized_protected_file(
                request.user,
                event,
                "snapshot_path",
            )
        except ProtectedAttachmentNotFound as exc:
            raise NotFound(str(exc)) from exc
        except ProtectedAttachmentAccessDenied as exc:
            raise PermissionDenied(str(exc)) from exc
        extension = PurePosixPath(protected_file.name).suffix.lower()
        filename = f"camera-event-{event.id}{extension}"
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return FileResponse(
            protected_file,
            as_attachment=True,
            filename=filename,
            content_type=content_type,
        )
