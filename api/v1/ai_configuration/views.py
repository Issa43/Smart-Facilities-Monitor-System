from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from drf_spectacular.utils import extend_schema

from api.v1.exceptions import DomainConflict
from apps.common.permissions import IsSuperAdmin
from apps.security.authentication import AIIngestionAuthentication
from apps.security.configuration import (
    create_configuration,
    currently_authorized_vehicle,
    disable_camera_ai_model,
    disable_configuration,
    enable_camera_ai_model,
    update_configuration,
)
from apps.security.machine_credentials import camera_for_ingestion
from apps.security.models import (
    AIIngestionCameraScope,
    AIIngestionCredential,
    AuthorizedVehicle,
    Camera,
    CameraAIModel,
    CameraROI,
    RestrictedZoneSchedule,
    VirtualLine,
)
from apps.security.permissions import IsAIIngestionMachine
from apps.security.throttling import AIIngestionRateThrottle

from .serializers import (
    AuthorizedVehicleReadSerializer,
    AuthorizedVehicleWriteSerializer,
    CameraAIModelInputSerializer,
    CameraAIModelReadSerializer,
    CameraROICreateSerializer,
    CameraROIReadSerializer,
    CameraROIUpdateSerializer,
    MachineAuthorizedVehicleSerializer,
    RestrictedScheduleCreateSerializer,
    RestrictedScheduleReadSerializer,
    RestrictedScheduleUpdateSerializer,
    VirtualLineCreateSerializer,
    VirtualLineReadSerializer,
    VirtualLineUpdateSerializer,
)


def _validation_error(error):
    details = getattr(error, "message_dict", None) or {
        "non_field_errors": error.messages
    }
    return ValidationError(detail=details)


def _machine_request(request):
    return isinstance(getattr(request, "auth", None), AIIngestionCredential)


def _scoped_camera_ids(credential):
    return AIIngestionCameraScope.objects.filter(
        credential=credential,
        camera__is_active=True,
        camera__facility__is_active=True,
    ).values("camera_id")


class ConfigurationAccessMixin:
    def initialize_request(self, request, *args, **kwargs):
        self._requested_method = request.method
        return super().initialize_request(request, *args, **kwargs)

    def get_authenticators(self):
        if getattr(self, "_requested_method", None) in {"GET", "HEAD", "OPTIONS"}:
            return [AIIngestionAuthentication(), JWTAuthentication()]
        return [JWTAuthentication()]

    def get_permissions(self):
        if self.request.method in {"GET", "HEAD", "OPTIONS"} and _machine_request(
            self.request
        ):
            return [IsAIIngestionMachine()]
        return [IsSuperAdmin()]

    def get_throttles(self):
        if _machine_request(self.request):
            return [AIIngestionRateThrottle()]
        return super().get_throttles()


class ConfigurationViewSet(ConfigurationAccessMixin, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]
    read_serializer_class = None
    create_serializer_class = None
    update_serializer_class = None
    audit_prefix = None

    def get_serializer_class(self):
        if self.action == "create":
            return self.create_serializer_class
        if self.action in {"update", "partial_update"}:
            return self.update_serializer_class
        return self.read_serializer_class

    def create(self, request, *args, **kwargs):
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            instance = create_configuration(
                model=self.queryset.model,
                values=dict(payload.validated_data),
                actor=request.user,
                action=f"{self.audit_prefix}.created",
            )
        except DjangoValidationError as exc:
            raise _validation_error(exc) from exc
        except IntegrityError as exc:
            raise DomainConflict("This configuration identity already exists.") from exc
        return Response(
            self.read_serializer_class(instance).data,
            status=status.HTTP_201_CREATED,
        )

    def _update(self, request, *, partial):
        instance = self.get_object()
        payload = self.get_serializer(instance, data=request.data, partial=partial)
        payload.is_valid(raise_exception=True)
        try:
            instance = update_configuration(
                instance=instance,
                values=dict(payload.validated_data),
                actor=request.user,
                action=f"{self.audit_prefix}.updated",
            )
        except DjangoValidationError as exc:
            raise _validation_error(exc) from exc
        except IntegrityError as exc:
            raise DomainConflict("This configuration identity already exists.") from exc
        return Response(self.read_serializer_class(instance).data)

    def update(self, request, *args, **kwargs):
        return self._update(request, partial=False)

    def partial_update(self, request, *args, **kwargs):
        return self._update(request, partial=True)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        disable_configuration(
            instance=instance,
            actor=request.user,
            action=f"{self.audit_prefix}.disabled",
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class CameraROIViewSet(ConfigurationViewSet):
    queryset = CameraROI.all_objects.select_related("camera__facility")
    read_serializer_class = CameraROIReadSerializer
    create_serializer_class = CameraROICreateSerializer
    update_serializer_class = CameraROIUpdateSerializer
    audit_prefix = "camera_roi"
    filterset_fields = ["camera"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if _machine_request(self.request):
            queryset = queryset.filter(
                is_active=True,
                camera_id__in=_scoped_camera_ids(self.request.auth),
            )
        camera_id = self.request.query_params.get("camera_id")
        return queryset.filter(camera_id=camera_id) if camera_id else queryset


class RestrictedScheduleViewSet(ConfigurationViewSet):
    queryset = RestrictedZoneSchedule.all_objects.select_related(
        "roi__camera__facility"
    )
    read_serializer_class = RestrictedScheduleReadSerializer
    create_serializer_class = RestrictedScheduleCreateSerializer
    update_serializer_class = RestrictedScheduleUpdateSerializer
    audit_prefix = "restricted_schedule"
    filterset_fields = ["roi"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if _machine_request(self.request):
            queryset = queryset.filter(
                is_active=True,
                roi__is_active=True,
                roi__camera_id__in=_scoped_camera_ids(self.request.auth),
            )
        camera_id = self.request.query_params.get("camera_id")
        return queryset.filter(roi__camera_id=camera_id) if camera_id else queryset


class VirtualLineViewSet(ConfigurationViewSet):
    queryset = VirtualLine.all_objects.select_related("camera__facility")
    read_serializer_class = VirtualLineReadSerializer
    create_serializer_class = VirtualLineCreateSerializer
    update_serializer_class = VirtualLineUpdateSerializer
    audit_prefix = "virtual_line"
    filterset_fields = ["camera"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if _machine_request(self.request):
            queryset = queryset.filter(
                is_active=True,
                camera_id__in=_scoped_camera_ids(self.request.auth),
            )
        camera_id = self.request.query_params.get("camera_id")
        return queryset.filter(camera_id=camera_id) if camera_id else queryset


class AuthorizedVehicleViewSet(ConfigurationViewSet):
    queryset = AuthorizedVehicle.all_objects.all()
    read_serializer_class = AuthorizedVehicleReadSerializer
    create_serializer_class = AuthorizedVehicleWriteSerializer
    update_serializer_class = AuthorizedVehicleWriteSerializer
    audit_prefix = "authorized_vehicle"
    filterset_fields = ["plate_number", "is_active"]

    def _machine_has_anpr_scope(self):
        return CameraAIModel.objects.filter(
            camera_id__in=_scoped_camera_ids(self.request.auth),
            model_identifier=CameraAIModel.ModelIdentifier.ANPR,
        ).exists()

    def get_queryset(self):
        queryset = super().get_queryset()
        if not _machine_request(self.request):
            return queryset
        if not self._machine_has_anpr_scope():
            return queryset.none()
        return queryset.filter(is_active=True).filter(
            Q(expires_on__isnull=True) | Q(expires_on__gte=timezone.localdate())
        )

    def get_serializer_class(self):
        if _machine_request(self.request) and self.action in {"list", "retrieve"}:
            return MachineAuthorizedVehicleSerializer
        return super().get_serializer_class()

    def list(self, request, *args, **kwargs):
        plate_number = request.query_params.get("plate_number")
        if _machine_request(request) and plate_number:
            if not self._machine_has_anpr_scope():
                raise PermissionDenied("ANPR configuration is not enabled for this credential.")
            vehicle = currently_authorized_vehicle(plate_number)
            return Response(
                {
                    "plate_number": AuthorizedVehicle.normalize_plate(plate_number),
                    "authorized": vehicle is not None,
                    "expires_on": vehicle.expires_on if vehicle else None,
                }
            )
        return super().list(request, *args, **kwargs)


class CameraActiveModelsView(ConfigurationAccessMixin, APIView):
    def _camera(self, request, camera_id):
        if _machine_request(request):
            try:
                return camera_for_ingestion(request.auth, camera_id)
            except DjangoValidationError as exc:
                raise PermissionDenied("Camera configuration is not available.") from exc
        return get_object_or_404(
            Camera.objects.select_related("facility"),
            pk=camera_id,
        )

    @extend_schema(responses=CameraAIModelReadSerializer(many=True))
    def get(self, request, camera_id):
        camera = self._camera(request, camera_id)
        assignments = CameraAIModel.objects.filter(camera=camera).order_by(
            "model_identifier"
        )
        return Response(CameraAIModelReadSerializer(assignments, many=True).data)

    @extend_schema(
        request=CameraAIModelInputSerializer,
        responses={200: CameraAIModelReadSerializer, 201: CameraAIModelReadSerializer},
    )
    def post(self, request, camera_id):
        camera = self._camera(request, camera_id)
        payload = CameraAIModelInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            assignment, changed = enable_camera_ai_model(
                camera=camera,
                model_identifier=payload.validated_data["model_identifier"],
                actor=request.user,
            )
        except DjangoValidationError as exc:
            raise _validation_error(exc) from exc
        return Response(
            CameraAIModelReadSerializer(assignment).data,
            status=status.HTTP_201_CREATED if changed else status.HTTP_200_OK,
        )


class CameraActiveModelDetailView(ConfigurationAccessMixin, APIView):
    @extend_schema(request=None, responses={204: None})
    def delete(self, request, camera_id, model_identifier):
        assignment = get_object_or_404(
            CameraAIModel.all_objects.select_related("camera__facility"),
            camera_id=camera_id,
            model_identifier=model_identifier,
        )
        try:
            disable_camera_ai_model(assignment=assignment, actor=request.user)
        except DjangoValidationError as exc:
            raise _validation_error(exc) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)
