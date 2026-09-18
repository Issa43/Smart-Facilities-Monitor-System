import logging

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.facilities.models import FacilityAssignment
from apps.security.models import CameraEvent, SecurityAlert
from apps.users.models import Role, User

from .models import DeviceRegistration, Notification, NotificationPreference, PushDelivery


logger = logging.getLogger(__name__)

ELIGIBLE_EVENT_TYPES = {
    CameraEvent.EventType.FIRE_ALERT,
    CameraEvent.EventType.SMOKE_ALERT,
    CameraEvent.EventType.INTRUSION_ALERT,
    CameraEvent.EventType.VEHICLE_ENTRY,
    CameraEvent.EventType.VEHICLE_EXIT,
    CameraEvent.EventType.TAMPER_ALERT,
}

ARABIC_ALERT_NAMES = {
    CameraEvent.EventType.FIRE_ALERT: "حريق",
    CameraEvent.EventType.SMOKE_ALERT: "دخان",
    CameraEvent.EventType.INTRUSION_ALERT: "دخول غير مصرح",
    CameraEvent.EventType.VEHICLE_ENTRY: "مركبة غير مصرح بها",
    CameraEvent.EventType.VEHICLE_EXIT: "مركبة غير مصرح بها",
    CameraEvent.EventType.TAMPER_ALERT: "عبث بالكاميرا",
}


def is_push_eligible_event(event):
    if event.event_type not in ELIGIBLE_EVENT_TYPES:
        return False
    if event.event_type in {
        CameraEvent.EventType.VEHICLE_ENTRY,
        CameraEvent.EventType.VEHICLE_EXIT,
    }:
        return event.authorized is False
    return True


def security_alert_recipient_ids(alert):
    opted_out = NotificationPreference.objects.filter(
        critical_alerts=False,
    ).values("user_id")
    return list(
        User.objects.filter(status=User.STATUS_ACTIVE, role__isnull=False)
        .filter(
            Q(role__name=Role.SUPER_ADMIN)
            | Q(
                role__name=Role.SECURITY_OFFICER,
                role__permissions__permission_name="alert.view",
                facility_assignments__facility_id=alert.facility_id,
                facility_assignments__is_active=True,
            )
        )
        .exclude(pk__in=opted_out)
        .values_list("pk", flat=True)
        .distinct()
    )


def user_can_receive_security_push(user, alert):
    if not user.is_active or not user.role_id:
        return False
    if NotificationPreference.objects.filter(
        user=user,
        critical_alerts=False,
    ).exists():
        return False
    if user.role.name == Role.SUPER_ADMIN:
        return True
    return bool(
        user.role.name == Role.SECURITY_OFFICER
        and user.role.permissions.filter(permission_name="alert.view").exists()
        and FacilityAssignment.objects.filter(
            facility_id=alert.facility_id,
            user=user,
            is_active=True,
        ).exists()
    )


def security_notification_content(alert, event):
    alert_name = ARABIC_ALERT_NAMES[event.event_type]
    return {
        "title": f"تحذير أمني — {alert_name}",
        "body": f"تم رصد {alert_name} في منشأة {alert.facility.name}.",
        "tone": (
            Notification.Tone.CRITICAL
            if alert.severity_level == SecurityAlert.Severity.CRITICAL
            else Notification.Tone.WARNING
        ),
    }


def security_push_payload(alert, event):
    return {
        "type": "security_alert",
        "alert_id": str(alert.pk),
        "event_type": event.event_type,
        "severity": alert.severity_level,
        "facility_id": str(alert.facility_id),
        "camera_id": str(event.camera_id),
    }


def create_security_alert_notifications(*, alert, event):
    """Persist recipient rows in the caller's alert-creation transaction."""
    if not is_push_eligible_event(event):
        return []
    content = security_notification_content(alert, event)
    notification_ids = []
    for recipient_id in security_alert_recipient_ids(alert):
        notification, _ = Notification.objects.get_or_create(
            deduplication_key=f"{recipient_id}:security-alert:{alert.pk}",
            defaults={
                "recipient_id": recipient_id,
                "title": content["title"],
                "body": content["body"],
                "category": Notification.Category.SECURITY,
                "tone": content["tone"],
                "href": f"/security/alerts/{alert.pk}",
                "source_type": alert._meta.label_lower,
                "source_id": alert.pk,
                "created_by_id": alert.created_by_id,
            },
        )
        notification_ids.append(notification.pk)

    if notification_ids:
        transaction.on_commit(
            lambda: enqueue_security_notifications(notification_ids),
            robust=True,
        )
    return notification_ids


def enqueue_security_notifications(notification_ids):
    from .tasks import deliver_push_notification

    notifications = Notification.objects.filter(
        pk__in=notification_ids,
        category=Notification.Category.SECURITY,
        source_type=SecurityAlert._meta.label_lower,
    ).select_related("recipient")
    for notification in notifications:
        devices = DeviceRegistration.objects.filter(
            user_id=notification.recipient_id,
            is_active=True,
        )
        for device in devices:
            delivery, _ = PushDelivery.objects.get_or_create(
                notification=notification,
                device=device,
            )
            if delivery.status == PushDelivery.Status.QUEUED:
                try:
                    deliver_push_notification.delay(str(delivery.pk))
                except Exception:
                    logger.exception(
                        "Unable to enqueue push delivery %s.",
                        delivery.pk,
                    )


@transaction.atomic
def register_device(*, user, token, platform, instance=None):
    now = timezone.now()
    token_hash = DeviceRegistration.hash_token(token)
    existing = (
        DeviceRegistration.all_objects.select_for_update()
        .filter(token_hash=token_hash)
        .first()
    )
    if existing is not None and existing.user_id != user.pk:
        raise ValueError("This device registration is not available.")
    if instance is not None and instance.user_id != user.pk:
        raise ValueError("This device registration is not available.")

    device = existing or instance
    if existing is not None and instance is not None and existing.pk != instance.pk:
        instance.is_active = False
        instance.disabled_at = now
        instance.save(update_fields=["is_active", "disabled_at", "updated_at"])
    if device is None:
        try:
            with transaction.atomic():
                return DeviceRegistration.objects.create(
                    user=user,
                    token=token,
                    platform=platform,
                    last_seen_at=now,
                    created_by=user,
                )
        except IntegrityError:
            device = (
                DeviceRegistration.all_objects.select_for_update()
                .filter(token_hash=token_hash)
                .first()
            )
            if device is None or device.user_id != user.pk:
                raise ValueError("This device registration is not available.")

    device.token = token
    device.platform = platform
    device.is_active = True
    device.disabled_at = None
    device.last_seen_at = now
    device.save(
        update_fields=[
            "token",
            "token_hash",
            "platform",
            "is_active",
            "disabled_at",
            "last_seen_at",
            "updated_at",
        ]
    )
    return device


def disable_device(device):
    device.is_active = False
    device.disabled_at = timezone.now()
    device.save(update_fields=["is_active", "disabled_at", "updated_at"])
