from decimal import Decimal

from drf_spectacular.utils import PolymorphicProxySerializer, inline_serializer
from rest_framework import serializers

from apps.security.models import CameraEvent


def _confidence():
    return serializers.DecimalField(
        max_digits=7,
        decimal_places=6,
        min_value=Decimal("0"),
        max_value=Decimal("1"),
    )


def _duration():
    return serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0"),
    )


def _common(event_type):
    return {
        "event_type": serializers.ChoiceField(choices=[event_type]),
        "camera_id": serializers.UUIDField(),
        "source_event_id": serializers.UUIDField(),
        "detected_at": serializers.DateTimeField(),
    }


def _tracked(event_type, object_class, *, intrusion=False):
    fields = {
        **_common(event_type),
        "roi_id": serializers.UUIDField(),
        "track_id": serializers.CharField(max_length=255),
        "class": serializers.ChoiceField(choices=[object_class]),
        "confidence": _confidence(),
        "bbox": serializers.JSONField(),
        "confirmed_at": serializers.DateTimeField(),
        "duration_seconds": _duration(),
        "snapshot_path": serializers.CharField(max_length=500),
    }
    if intrusion:
        fields.update(
            entered_roi_at=serializers.DateTimeField(),
            time_restricted=serializers.ChoiceField(choices=[True]),
        )
    return fields


def _vehicle(event_type, direction):
    return {
        **_common(event_type),
        "track_id": serializers.CharField(max_length=255),
        "plate_number": serializers.CharField(max_length=32),
        "plate_confidence": _confidence(),
        "ocr_confidence": _confidence(),
        "vehicle_type": serializers.ChoiceField(
            choices=CameraEvent.VehicleType.choices
        ),
        "vehicle_confidence": _confidence(),
        "direction": serializers.ChoiceField(choices=[direction]),
        "crossing_centroid": serializers.JSONField(),
        "authorized": serializers.BooleanField(),
        "bbox_plate": serializers.JSONField(),
        "bbox_vehicle": serializers.JSONField(),
        "snapshot_path": serializers.CharField(max_length=500),
    }


CAMERA_EVENT_CREATE_REQUEST = PolymorphicProxySerializer(
    component_name="CameraEventCreateRequest",
    resource_type_field_name="event_type",
    serializers=[
        inline_serializer(
            name="FireCameraEventRequest",
            fields=_tracked(CameraEvent.EventType.FIRE_ALERT, "fire"),
        ),
        inline_serializer(
            name="SmokeCameraEventRequest",
            fields=_tracked(CameraEvent.EventType.SMOKE_ALERT, "smoke"),
        ),
        inline_serializer(
            name="IntrusionCameraEventRequest",
            fields=_tracked(
                CameraEvent.EventType.INTRUSION_ALERT,
                "person",
                intrusion=True,
            ),
        ),
        inline_serializer(
            name="VehicleEntryCameraEventRequest",
            fields=_vehicle(
                CameraEvent.EventType.VEHICLE_ENTRY,
                CameraEvent.Direction.ENTRY,
            ),
        ),
        inline_serializer(
            name="VehicleExitCameraEventRequest",
            fields=_vehicle(
                CameraEvent.EventType.VEHICLE_EXIT,
                CameraEvent.Direction.EXIT,
            ),
        ),
        inline_serializer(
            name="TamperCameraEventRequest",
            fields={
                **_common(CameraEvent.EventType.TAMPER_ALERT),
                "tamper_type": serializers.ChoiceField(
                    choices=CameraEvent.TamperType.choices
                ),
                "confidence": _confidence(),
                "snapshot_path": serializers.CharField(
                    max_length=500,
                    required=False,
                    allow_null=True,
                ),
            },
        ),
    ],
)
