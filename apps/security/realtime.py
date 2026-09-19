import logging
from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q

from apps.users.models import Role, User

from .models import CameraEvent, SecurityAlert


logger = logging.getLogger(__name__)
LIVE_PROTOCOL_VERSION = 1


def security_user_group(user_id):
    return f"security.user.{user_id}"


def _serialized(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _alert_contract(alert, *, event=None):
    if alert is None:
        return None
    return {
        "id": str(alert.pk),
        "event_id": str(event.pk) if event else None,
        "facility_id": str(alert.facility_id),
        "camera_id": str(event.camera_id) if event else None,
        "alert_type": alert.alert_type,
        "severity": alert.severity_level,
        "status": alert.status,
        "is_false_positive": alert.is_false_positive,
        "created_at": _serialized(alert.created_at),
        "updated_at": _serialized(alert.updated_at),
    }


def camera_event_created_contract(event):
    alert = event.security_alert if event.security_alert_id else None
    return {
        "type": "security.camera_event.created",
        "version": LIVE_PROTOCOL_VERSION,
        "event": {
            "id": str(event.pk),
            "event_type": event.event_type,
            "camera_id": str(event.camera_id),
            "facility_id": str(event.camera.facility_id),
            "roi_id": str(event.roi_id) if event.roi_id else None,
            "track_id": event.track_id,
            "object_class": event.object_class,
            "confidence": _serialized(event.confidence),
            "detected_at": _serialized(event.detected_at),
            "confirmed_at": _serialized(event.confirmed_at),
            "duration_seconds": _serialized(event.duration_seconds),
            "authorized": event.authorized,
            "direction": event.direction,
            "plate_number": event.plate_number,
            "tamper_type": event.tamper_type,
            "security_alert_id": (
                str(event.security_alert_id) if event.security_alert_id else None
            ),
            "status": event.status,
            "snapshot": {
                "available": bool(event.snapshot_path),
                "download_path": (
                    f"/api/v1/camera-events/{event.pk}/snapshot/"
                    if event.snapshot_path
                    else None
                ),
            },
        },
        "security_alert": _alert_contract(alert, event=event),
    }


def security_alert_updated_contract(alert):
    try:
        event = alert.camera_event
    except ObjectDoesNotExist:
        event = None
    return {
        "type": "security.alert.updated",
        "version": LIVE_PROTOCOL_VERSION,
        "alert": _alert_contract(alert, event=event),
    }


def _recipient_ids(facility_id):
    return list(
        User.objects.filter(status=User.STATUS_ACTIVE, role__isnull=False)
        .filter(
            Q(role__name=Role.SUPER_ADMIN)
            | Q(
                role__name=Role.SECURITY_OFFICER,
                role__permissions__permission_name="alert.view",
                facility_assignments__facility_id=facility_id,
                facility_assignments__is_active=True,
            )
        )
        .values_list("pk", flat=True)
        .distinct()
    )


def _broadcast(payload, facility_id):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.error("Security live event skipped because no channel layer is configured.")
        return
    for user_id in _recipient_ids(facility_id):
        try:
            async_to_sync(channel_layer.group_send)(
                security_user_group(user_id),
                {"type": "security.message", "payload": payload},
            )
        except Exception:
            logger.exception("Security live event delivery failed.")


def broadcast_camera_event_created(event_id):
    event = CameraEvent.objects.select_related(
        "camera__facility",
        "roi",
        "security_alert",
    ).get(pk=event_id)
    _broadcast(camera_event_created_contract(event), event.camera.facility_id)


def broadcast_security_alert_updated(alert_id):
    alert = SecurityAlert.objects.select_related(
        "facility",
        "camera_event__camera__facility",
    ).get(pk=alert_id)
    _broadcast(security_alert_updated_contract(alert), alert.facility_id)


def schedule_camera_event_created_broadcast(event_id):
    transaction.on_commit(
        lambda: broadcast_camera_event_created(event_id),
        robust=True,
    )


def schedule_security_alert_updated_broadcast(alert_id):
    transaction.on_commit(
        lambda: broadcast_security_alert_updated(alert_id),
        robust=True,
    )
