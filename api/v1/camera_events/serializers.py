import math
from decimal import Decimal

from rest_framework import serializers
from rest_framework.reverse import reverse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from apps.security.models import AuthorizedVehicle, CameraEvent


COORDINATE_SHAPES = {
    "bbox": ("x1", "y1", "x2", "y2"),
    "bbox_plate": ("x1", "y1", "x2", "y2"),
    "bbox_vehicle": ("x1", "y1", "x2", "y2"),
    "crossing_centroid": ("x", "y"),
}
VEHICLE_FIELDS = {
    "bbox_plate",
    "bbox_vehicle",
    "crossing_centroid",
    "plate_number",
    "plate_confidence",
    "ocr_confidence",
    "vehicle_type",
    "vehicle_confidence",
    "direction",
    "authorized",
}
INTRUSION_FIELDS = {"entered_roi_at", "time_restricted"}
TRACKED_DETECTION_FIELDS = {
    "roi_id",
    "track_id",
    "object_class",
    "confidence",
    "bbox",
    "confirmed_at",
    "duration_seconds",
    "snapshot_path",
}
INTRUSION_REQUIRED_FIELDS = TRACKED_DETECTION_FIELDS | INTRUSION_FIELDS
VEHICLE_REQUIRED_FIELDS = {
    "track_id",
    "plate_number",
    "plate_confidence",
    "ocr_confidence",
    "vehicle_type",
    "vehicle_confidence",
    "direction",
    "crossing_centroid",
    "authorized",
    "bbox_plate",
    "bbox_vehicle",
    "snapshot_path",
}
TAMPER_FORBIDDEN_FIELDS = {
    "roi_id",
    "track_id",
    "object_class",
    "bbox",
    "confirmed_at",
    "duration_seconds",
    *INTRUSION_FIELDS,
    *VEHICLE_FIELDS,
}
COMMON_IDENTITY_FIELDS = {"event_type", "camera", "source_event_id", "detected_at"}
EVENT_ALLOWED_FIELDS = {
    CameraEvent.EventType.FIRE_ALERT: COMMON_IDENTITY_FIELDS
    | TRACKED_DETECTION_FIELDS,
    CameraEvent.EventType.SMOKE_ALERT: COMMON_IDENTITY_FIELDS
    | TRACKED_DETECTION_FIELDS,
    CameraEvent.EventType.INTRUSION_ALERT: COMMON_IDENTITY_FIELDS
    | INTRUSION_REQUIRED_FIELDS,
    CameraEvent.EventType.VEHICLE_ENTRY: COMMON_IDENTITY_FIELDS
    | VEHICLE_REQUIRED_FIELDS,
    CameraEvent.EventType.VEHICLE_EXIT: COMMON_IDENTITY_FIELDS
    | VEHICLE_REQUIRED_FIELDS,
    CameraEvent.EventType.TAMPER_ALERT: COMMON_IDENTITY_FIELDS
    | {"tamper_type", "confidence", "snapshot_path"},
}

EXTERNAL_FIELD_NAMES = {
    "camera": "camera_id",
    "object_class": "class",
}


def external_field_name(field):
    return EXTERNAL_FIELD_NAMES.get(field, field)


def require_non_null_fields(attrs, field_names, errors):
    for field in field_names:
        if attrs.get(field) is None:
            public_field = external_field_name(field)
            errors[public_field] = (
                f"{public_field} is required for this event type."
            )


def validate_coordinates(field_name, value):
    if value is None:
        return value
    expected = COORDINATE_SHAPES[field_name]
    if not isinstance(value, dict) or set(value) != set(expected):
        raise serializers.ValidationError(
            f"{field_name} must contain exactly: {', '.join(expected)}."
        )
    for key in expected:
        coordinate = value[key]
        if (
            isinstance(coordinate, bool)
            or not isinstance(coordinate, (int, float))
            or not math.isfinite(coordinate)
            or coordinate < 0
        ):
            raise serializers.ValidationError(
                f"{field_name}.{key} must be a finite non-negative number."
            )
    if field_name != "crossing_centroid" and (
        value["x2"] < value["x1"] or value["y2"] < value["y1"]
    ):
        raise serializers.ValidationError(
            f"{field_name} maximum coordinates must not precede minimum coordinates."
        )
    return value


class StrictInputSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not hasattr(data, "keys"):
            raise serializers.ValidationError("Expected an object payload.")
        unknown = sorted(set(data.keys()) - set(self.fields))
        if unknown:
            raise serializers.ValidationError(
                {field: "This field is not allowed." for field in unknown}
            )
        return super().to_internal_value(data)


class CameraEventCreateSerializer(StrictInputSerializer):
    event_type = serializers.ChoiceField(choices=CameraEvent.EventType.choices)
    camera_id = serializers.UUIDField(source="camera")
    roi_id = serializers.UUIDField(required=False, allow_null=True)
    source_event_id = serializers.UUIDField()
    track_id = serializers.CharField(max_length=255, required=False, allow_null=True)
    confidence = serializers.DecimalField(
        max_digits=7,
        decimal_places=6,
        min_value=Decimal("0"),
        max_value=Decimal("1"),
        required=False,
        allow_null=True,
    )
    class_value = serializers.CharField(
        source="object_class",
        max_length=100,
        required=False,
        allow_null=True,
        allow_blank=False,
    )
    detected_at = serializers.DateTimeField()
    confirmed_at = serializers.DateTimeField(required=False, allow_null=True)
    duration_seconds = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0"),
        required=False,
        allow_null=True,
    )
    snapshot_path = serializers.CharField(
        max_length=500,
        required=False,
        allow_null=True,
        allow_blank=False,
    )
    bbox = serializers.JSONField(required=False, allow_null=True)
    bbox_plate = serializers.JSONField(required=False, allow_null=True)
    bbox_vehicle = serializers.JSONField(required=False, allow_null=True)
    crossing_centroid = serializers.JSONField(required=False, allow_null=True)
    entered_roi_at = serializers.DateTimeField(required=False, allow_null=True)
    time_restricted = serializers.BooleanField(required=False, allow_null=True)
    plate_number = serializers.CharField(
        max_length=32,
        required=False,
        allow_null=True,
        allow_blank=False,
    )
    plate_confidence = serializers.DecimalField(
        max_digits=7,
        decimal_places=6,
        min_value=Decimal("0"),
        max_value=Decimal("1"),
        required=False,
        allow_null=True,
    )
    ocr_confidence = serializers.DecimalField(
        max_digits=7,
        decimal_places=6,
        min_value=Decimal("0"),
        max_value=Decimal("1"),
        required=False,
        allow_null=True,
    )
    vehicle_type = serializers.ChoiceField(
        choices=CameraEvent.VehicleType.choices,
        required=False,
        allow_null=True,
    )
    vehicle_confidence = serializers.DecimalField(
        max_digits=7,
        decimal_places=6,
        min_value=Decimal("0"),
        max_value=Decimal("1"),
        required=False,
        allow_null=True,
    )
    direction = serializers.ChoiceField(
        choices=CameraEvent.Direction.choices,
        required=False,
        allow_null=True,
    )
    authorized = serializers.BooleanField(required=False, allow_null=True)
    tamper_type = serializers.ChoiceField(
        choices=CameraEvent.TamperType.choices,
        required=False,
        allow_null=True,
    )

    def get_fields(self):
        fields = super().get_fields()
        fields["class"] = fields.pop("class_value")
        return fields

    def validate(self, attrs):
        for field in COORDINATE_SHAPES:
            if field in attrs:
                attrs[field] = validate_coordinates(field, attrs[field])

        event_type = attrs["event_type"]
        errors = {}
        for field in set(attrs) - EVENT_ALLOWED_FIELDS[event_type]:
            if attrs.get(field) is not None:
                errors[external_field_name(field)] = (
                    "This field is not valid for this event type."
                )
        required_class = {
            CameraEvent.EventType.FIRE_ALERT: "fire",
            CameraEvent.EventType.SMOKE_ALERT: "smoke",
            CameraEvent.EventType.INTRUSION_ALERT: "person",
        }.get(event_type)
        if required_class and (attrs.get("object_class") or "").lower() != required_class:
            errors["class"] = f"{event_type} requires class={required_class}."

        if event_type in {
            CameraEvent.EventType.FIRE_ALERT,
            CameraEvent.EventType.SMOKE_ALERT,
        }:
            require_non_null_fields(attrs, TRACKED_DETECTION_FIELDS, errors)

        is_vehicle = event_type in {
            CameraEvent.EventType.VEHICLE_ENTRY,
            CameraEvent.EventType.VEHICLE_EXIT,
        }
        if is_vehicle:
            if attrs.get("roi_id") is not None:
                errors["roi_id"] = "Vehicle events do not use ROI configuration."
            require_non_null_fields(attrs, VEHICLE_REQUIRED_FIELDS, errors)
            normalized_plate = AuthorizedVehicle.normalize_plate(
                attrs.get("plate_number")
            )
            if normalized_plate:
                attrs["plate_number"] = normalized_plate
            expected_direction = (
                CameraEvent.Direction.ENTRY
                if event_type == CameraEvent.EventType.VEHICLE_ENTRY
                else CameraEvent.Direction.EXIT
            )
            if attrs.get("direction") and attrs["direction"] != expected_direction:
                errors["direction"] = f"{event_type} requires direction={expected_direction}."
        else:
            for field in VEHICLE_FIELDS:
                if attrs.get(field) is not None:
                    errors[field] = "This field is only valid for vehicle events."

        if event_type == CameraEvent.EventType.INTRUSION_ALERT:
            require_non_null_fields(attrs, INTRUSION_REQUIRED_FIELDS, errors)
            if attrs.get("time_restricted") is not True:
                errors["time_restricted"] = (
                    "intrusion_alert requires time_restricted=true."
                )
        else:
            for field in INTRUSION_FIELDS:
                if attrs.get(field) is not None:
                    errors[field] = "This field is only valid for intrusion events."

        if event_type == CameraEvent.EventType.TAMPER_ALERT:
            require_non_null_fields(attrs, {"confidence", "tamper_type"}, errors)
            if attrs.get("tamper_type") is None:
                errors["tamper_type"] = "tamper_type is required for tamper alerts."
            for field in TAMPER_FORBIDDEN_FIELDS:
                if attrs.get(field) is not None:
                    errors[external_field_name(field)] = (
                        "This field is not valid for tamper alerts."
                    )
        elif attrs.get("tamper_type") is not None:
            errors["tamper_type"] = "tamper_type is only valid for tamper alerts."

        detected_at = attrs["detected_at"]
        confirmed_at = attrs.get("confirmed_at")
        if confirmed_at and confirmed_at < detected_at:
            errors["confirmed_at"] = "confirmed_at cannot precede detected_at."
        entered_roi_at = attrs.get("entered_roi_at")
        if entered_roi_at and entered_roi_at < detected_at:
            errors["entered_roi_at"] = "entered_roi_at cannot precede detected_at."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class CameraEventPatchSerializer(StrictInputSerializer):
    confidence = serializers.DecimalField(
        max_digits=7,
        decimal_places=6,
        min_value=Decimal("0"),
        max_value=Decimal("1"),
        required=False,
        allow_null=True,
    )
    bbox = serializers.JSONField(required=False, allow_null=True)
    duration_seconds = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0"),
        required=False,
        allow_null=True,
    )
    confirmed_at = serializers.DateTimeField(required=False, allow_null=True)
    snapshot_path = serializers.CharField(
        max_length=500,
        required=False,
        allow_null=True,
        allow_blank=False,
    )

    def validate_bbox(self, value):
        return validate_coordinates("bbox", value)

    def validate(self, attrs):
        event = self.context.get("event")
        if event and attrs.get("confirmed_at") and attrs["confirmed_at"] < event.detected_at:
            raise serializers.ValidationError(
                {"confirmed_at": "confirmed_at cannot precede detected_at."}
            )
        if not attrs:
            raise serializers.ValidationError("At least one mutable field is required.")
        return attrs


class CameraEventReadSerializer(serializers.ModelSerializer):
    camera_id = serializers.UUIDField(read_only=True)
    camera_code = serializers.CharField(source="camera.code", read_only=True)
    facility_id = serializers.UUIDField(source="camera.facility_id", read_only=True)
    facility_name = serializers.CharField(source="camera.facility.name", read_only=True)
    roi_id = serializers.UUIDField(read_only=True)
    roi_identifier = serializers.CharField(source="roi.identifier", read_only=True)
    ingestion_key_id = serializers.CharField(
        source="ingestion_credential.key_id", read_only=True
    )
    security_alert_id = serializers.UUIDField(read_only=True)
    status = serializers.CharField(read_only=True)
    snapshot_available = serializers.SerializerMethodField()
    snapshot_download_url = serializers.SerializerMethodField()

    class Meta:
        model = CameraEvent
        fields = [
            "id",
            "event_type",
            "camera_id",
            "camera_code",
            "facility_id",
            "facility_name",
            "roi_id",
            "roi_identifier",
            "ingestion_key_id",
            "source_event_id",
            "track_id",
            "confidence",
            "object_class",
            "detected_at",
            "confirmed_at",
            "duration_seconds",
            "bbox",
            "bbox_plate",
            "bbox_vehicle",
            "crossing_centroid",
            "entered_roi_at",
            "time_restricted",
            "plate_number",
            "plate_confidence",
            "ocr_confidence",
            "vehicle_type",
            "vehicle_confidence",
            "direction",
            "authorized",
            "tamper_type",
            "status",
            "security_alert_id",
            "snapshot_available",
            "snapshot_download_url",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_snapshot_available(self, event):
        return bool(event.snapshot_path)

    @extend_schema_field(OpenApiTypes.URI)
    def get_snapshot_download_url(self, event):
        if not event.snapshot_path:
            return None
        return reverse(
            "api_v1:camera-event-snapshot",
            kwargs={"pk": event.pk},
            request=self.context.get("request"),
        )
