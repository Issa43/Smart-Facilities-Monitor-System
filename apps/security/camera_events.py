from decimal import Decimal
from pathlib import PurePosixPath

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.attachments.storage import get_protected_storage
from apps.audit.services import record_audit
from apps.notifications.push import create_security_alert_notifications

from .configuration import currently_authorized_vehicle
from .machine_credentials import camera_for_ingestion, can_ingest_camera_event
from .models import (
    CameraEvent,
    CameraROI,
    SecurityAlert,
    VirtualLine,
    validate_security_snapshot,
)
from .realtime import schedule_camera_event_created_broadcast


ALERT_TYPE_BY_EVENT = {
    CameraEvent.EventType.FIRE_ALERT: SecurityAlert.AlertType.FIRE,
    CameraEvent.EventType.SMOKE_ALERT: SecurityAlert.AlertType.SMOKE,
    CameraEvent.EventType.INTRUSION_ALERT: SecurityAlert.AlertType.INTRUSION,
    CameraEvent.EventType.VEHICLE_ENTRY: SecurityAlert.AlertType.VEHICLE,
    CameraEvent.EventType.VEHICLE_EXIT: SecurityAlert.AlertType.VEHICLE,
    CameraEvent.EventType.TAMPER_ALERT: SecurityAlert.AlertType.TAMPER,
}
SEVERITY_BY_EVENT = {
    CameraEvent.EventType.FIRE_ALERT: SecurityAlert.Severity.CRITICAL,
    CameraEvent.EventType.SMOKE_ALERT: SecurityAlert.Severity.CRITICAL,
    CameraEvent.EventType.INTRUSION_ALERT: SecurityAlert.Severity.HIGH,
    CameraEvent.EventType.VEHICLE_ENTRY: SecurityAlert.Severity.HIGH,
    CameraEvent.EventType.VEHICLE_EXIT: SecurityAlert.Severity.HIGH,
    CameraEvent.EventType.TAMPER_ALERT: SecurityAlert.Severity.CRITICAL,
}

CREATE_FIELDS = (
    "event_type",
    "roi",
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
)
MUTABLE_FIELDS = {
    "confidence",
    "bbox",
    "duration_seconds",
    "confirmed_at",
    "snapshot_path",
}


class CameraEventConflict(ValidationError):
    pass


def validate_snapshot_path(snapshot_path, camera):
    if not snapshot_path:
        return None
    value = str(snapshot_path)
    lowered = value.lower()
    if (
        "\\" in value
        or "://" in lowered
        or value.startswith("/")
        or (len(value) > 1 and value[1] == ":")
    ):
        raise ValidationError({"snapshot_path": "Invalid protected snapshot key."})

    path = PurePosixPath(value)
    expected_prefix = (
        "security",
        "camera-events",
        str(camera.facility_id),
        str(camera.pk),
    )
    if (
        path.is_absolute()
        or ".." in path.parts
        or len(path.parts) != 5
        or tuple(path.parts[:4]) != expected_prefix
        or path.suffix.lower() != ".jpg"
        or not path.stem
        or not all(character.isalnum() or character in {"-", "_"} for character in path.stem)
    ):
        raise ValidationError({"snapshot_path": "Invalid protected snapshot key."})

    storage = get_protected_storage()
    try:
        exists = storage.exists(value)
    except OSError as exc:
        raise ValidationError(
            {"snapshot_path": "Protected snapshot is unavailable."}
        ) from exc
    if not exists:
        raise ValidationError({"snapshot_path": "Protected snapshot is unavailable."})

    try:
        with storage.open(value, "rb") as snapshot:
            validate_security_snapshot(snapshot)
    except (OSError, ValidationError) as exc:
        if isinstance(exc, ValidationError):
            raise ValidationError({"snapshot_path": exc.messages}) from exc
        raise ValidationError(
            {"snapshot_path": "Protected snapshot is unavailable."}
        ) from exc
    return value


def _event_is_alertable(data):
    event_type = data["event_type"]
    if event_type in {
        CameraEvent.EventType.VEHICLE_ENTRY,
        CameraEvent.EventType.VEHICLE_EXIT,
    }:
        return data.get("authorized") is False
    return True


def _same_create_payload(event, camera, data, snapshot_path):
    if event.camera_id != camera.pk:
        return False
    for field in CREATE_FIELDS:
        if getattr(event, field) != data.get(field):
            return False
    return (event.snapshot_path.name if event.snapshot_path else None) == snapshot_path


def _safe_event_audit(event):
    return {
        "event_type": event.event_type,
        "camera_id": str(event.camera_id),
        "facility_id": str(event.camera.facility_id),
        "credential_id": str(event.ingestion_credential_id),
        "source_event_id": str(event.source_event_id),
        "roi_id": str(event.roi_id) if event.roi_id else None,
        "security_alert_id": (
            str(event.security_alert_id) if event.security_alert_id else None
        ),
    }


def _create_security_alert(event):
    alert = SecurityAlert(
        facility=event.camera.facility,
        alert_type=ALERT_TYPE_BY_EVENT[event.event_type],
        location=event.camera.zone or event.camera.name,
        severity_level=SEVERITY_BY_EVENT[event.event_type],
        source=SecurityAlert.Source.AI_DETECTION,
        confidence_score=(
            event.confidence.quantize(Decimal("0.0001"))
            if event.confidence is not None
            else None
        ),
    )
    alert.full_clean()
    alert.save()
    event.security_alert = alert
    event.save(update_fields=["security_alert", "updated_at"])
    create_security_alert_notifications(alert=alert, event=event)
    record_audit(
        actor=event.ingestion_credential.principal,
        action="security_alert.created_from_camera_event",
        entity=alert,
        after={
            "camera_event_id": str(event.pk),
            "camera_id": str(event.camera_id),
            "facility_id": str(event.camera.facility_id),
            "alert_type": alert.alert_type,
            "severity_level": alert.severity_level,
        },
    )
    return alert


def _existing_or_conflict(credential, source_event_id, camera, data, snapshot_path):
    event = (
        CameraEvent.all_objects.select_related(
            "camera__facility",
            "ingestion_credential__principal",
            "roi",
            "security_alert",
        )
        .filter(
            ingestion_credential=credential,
            source_event_id=source_event_id,
        )
        .first()
    )
    if event is None:
        return None
    if not _same_create_payload(event, camera, data, snapshot_path):
        raise CameraEventConflict(
            {"source_event_id": "This event identity already has a different payload."}
        )
    return event


def create_camera_event(*, credential, source_event_id, camera_id, data):
    camera = camera_for_ingestion(credential, camera_id)
    if data["event_type"] in {
        CameraEvent.EventType.VEHICLE_ENTRY,
        CameraEvent.EventType.VEHICLE_EXIT,
    } and not VirtualLine.objects.filter(camera=camera).exists():
        raise ValidationError(
            {
                "camera_id": (
                    "Vehicle events require an active virtual line for the camera."
                )
            }
        )
    event_data = {field: data.get(field) for field in CREATE_FIELDS}
    roi_id = data.get("roi_id")
    if roi_id:
        roi = CameraROI.objects.filter(pk=roi_id, camera=camera).first()
        if roi is None:
            raise ValidationError(
                {"roi_id": "ROI is not active for the authorized event camera."}
            )
        event_data["roi"] = roi
    else:
        event_data["roi"] = None
    submitted_snapshot_path = data.get("snapshot_path") or None

    existing = _existing_or_conflict(
        credential,
        source_event_id,
        camera,
        event_data,
        submitted_snapshot_path,
    )
    if existing is not None:
        return existing, False
    if data["event_type"] in {
        CameraEvent.EventType.VEHICLE_ENTRY,
        CameraEvent.EventType.VEHICLE_EXIT,
    }:
        registry_authorized = currently_authorized_vehicle(data.get("plate_number")) is not None
        if data.get("authorized") is not registry_authorized:
            raise ValidationError(
                {
                    "authorized": (
                        "authorized must match the server-owned active authorized-vehicle registry."
                    )
                }
            )
        event_data["authorized"] = registry_authorized
    snapshot_path = validate_snapshot_path(submitted_snapshot_path, camera)

    try:
        with transaction.atomic():
            event = CameraEvent(
                camera=camera,
                ingestion_credential=credential,
                source_event_id=source_event_id,
                snapshot_path=snapshot_path,
                created_by=credential.principal,
                **event_data,
            )
            # The database uniqueness constraint is the race-safe idempotency gate.
            event.full_clean(validate_unique=False, validate_constraints=False)
            event.save()
            if _event_is_alertable(event_data):
                _create_security_alert(event)
            record_audit(
                actor=credential.principal,
                action="camera_event.created",
                entity=event,
                after=_safe_event_audit(event),
            )
            schedule_camera_event_created_broadcast(event.pk)
        return event, True
    except IntegrityError as exc:
        existing = _existing_or_conflict(
            credential, source_event_id, camera, event_data, snapshot_path
        )
        if existing is not None:
            return existing, False
        raise CameraEventConflict(
            {"source_event_id": "The event changed concurrently; retry the request."}
        ) from exc


@transaction.atomic
def update_camera_event(*, event_id, credential, changes):
    forbidden = sorted(set(changes) - MUTABLE_FIELDS)
    if forbidden:
        raise ValidationError(
            {field: "This CameraEvent field is immutable." for field in forbidden}
        )
    event = (
        CameraEvent.objects.select_for_update(of=("self",))
        .select_related(
            "camera__facility",
            "ingestion_credential__principal",
            "roi",
            "security_alert",
        )
        .filter(pk=event_id, ingestion_credential=credential)
        .first()
    )
    if event is None or not can_ingest_camera_event(credential, getattr(event, "camera", None)):
        raise ValidationError({"event": "Camera event is not available for update."})

    if "snapshot_path" in changes:
        changes["snapshot_path"] = validate_snapshot_path(
            changes["snapshot_path"], event.camera
        )
    for field, value in changes.items():
        setattr(event, field, value)
    event.full_clean()
    event.save(update_fields=[*changes.keys(), "updated_at"])
    return event
