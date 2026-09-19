from datetime import timedelta
import logging

from celery import shared_task
from django.core.exceptions import ValidationError
from django.db import InterfaceError, OperationalError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.facilities.models import FacilityAssignment
from apps.maintenance.models import MaintenanceOrder
from apps.projects.models import Project
from apps.security.models import SecurityAlert
from apps.security.services import convert_alert_to_incident, review_security_alert
from apps.users.models import Role, User

from .fcm import FCMUnavailable, send_push
from .models import Notification, PushDelivery
from .push import (
    is_push_eligible_event,
    security_alert_recipient_ids,
    security_push_payload,
    user_can_receive_security_push,
)
from .services import notify_users, setting_enabled


logger = logging.getLogger(__name__)
TRANSIENT_TASK_ERRORS = (OperationalError, InterfaceError, OSError, ConnectionError, TimeoutError)
PROJECT_COMPLETION_MILESTONES = {30, 14, 7, 0}
PUSH_MAX_RETRIES = 5


class TransientPushDeliveryError(RuntimeError):
    pass


def _finish_push_delivery(delivery_id, status, *, failure_code="", message_id=""):
    PushDelivery.all_objects.filter(pk=delivery_id).update(
        status=status,
        failure_code=failure_code,
        provider_message_id=message_id,
        processing_started_at=None,
        sent_at=timezone.now() if status == PushDelivery.Status.SENT else None,
        updated_at=timezone.now(),
    )


@shared_task(
    bind=True,
    name="notifications.deliver_push_notification",
    max_retries=PUSH_MAX_RETRIES,
    acks_late=True,
)
def deliver_push_notification(self, delivery_id):
    """Deliver one Notification to one device without exposing its token."""
    from firebase_admin import exceptions as firebase_exceptions
    from firebase_admin import messaging

    with transaction.atomic():
        delivery = (
            # Lock only this delivery row; the nullable role joins cannot be
            # locked on PostgreSQL.
            PushDelivery.all_objects.select_for_update(of=("self",))
            .select_related(
                "notification__recipient__role",
                "device__user__role",
            )
            .filter(pk=delivery_id)
            .first()
        )
        if delivery is None or delivery.status in {
            PushDelivery.Status.SENT,
            PushDelivery.Status.INVALID_TOKEN,
            PushDelivery.Status.FAILED,
            PushDelivery.Status.SKIPPED,
            PushDelivery.Status.PROCESSING,
        }:
            return delivery.status if delivery is not None else "missing"
        delivery.status = PushDelivery.Status.PROCESSING
        delivery.processing_started_at = timezone.now()
        delivery.attempt_count += 1
        delivery.failure_code = ""
        delivery.save(
            update_fields=[
                "status",
                "processing_started_at",
                "attempt_count",
                "failure_code",
                "updated_at",
            ]
        )

    notification = delivery.notification
    device = delivery.device
    alert = (
        SecurityAlert.objects.select_related("facility", "camera_event__camera")
        .filter(
            pk=notification.source_id,
            source=SecurityAlert.Source.AI_DETECTION,
        )
        .first()
    )
    event = getattr(alert, "camera_event", None) if alert is not None else None
    if (
        not notification.is_active
        or notification.recipient_id != device.user_id
        or not device.is_active
        or alert is None
        or event is None
        or not is_push_eligible_event(event)
        or not user_can_receive_security_push(device.user, alert)
    ):
        _finish_push_delivery(
            delivery.pk,
            PushDelivery.Status.SKIPPED,
            failure_code="recipient_ineligible",
        )
        return PushDelivery.Status.SKIPPED

    transient_errors = (
        firebase_exceptions.AbortedError,
        firebase_exceptions.DeadlineExceededError,
        firebase_exceptions.InternalError,
        firebase_exceptions.ResourceExhaustedError,
        firebase_exceptions.UnavailableError,
        OSError,
        ConnectionError,
        TimeoutError,
    )
    try:
        message_id = send_push(
            token=device.token,
            title=notification.title,
            body=notification.body,
            data=security_push_payload(alert, event),
        )
    except messaging.UnregisteredError:
        device.is_active = False
        device.disabled_at = timezone.now()
        device.save(update_fields=["is_active", "disabled_at", "updated_at"])
        _finish_push_delivery(
            delivery.pk,
            PushDelivery.Status.INVALID_TOKEN,
            failure_code="unregistered_token",
        )
        return PushDelivery.Status.INVALID_TOKEN
    except FCMUnavailable:
        _finish_push_delivery(
            delivery.pk,
            PushDelivery.Status.FAILED,
            failure_code="fcm_unavailable",
        )
        return PushDelivery.Status.FAILED
    except transient_errors:
        if self.request.retries >= PUSH_MAX_RETRIES:
            _finish_push_delivery(
                delivery.pk,
                PushDelivery.Status.FAILED,
                failure_code="transient_exhausted",
            )
            return PushDelivery.Status.FAILED
        _finish_push_delivery(
            delivery.pk,
            PushDelivery.Status.QUEUED,
            failure_code="transient_provider_error",
        )
        raise self.retry(
            exc=TransientPushDeliveryError("Transient push delivery failure."),
            countdown=min(300, 2 ** (self.request.retries + 1)),
        )
    except Exception:
        _finish_push_delivery(
            delivery.pk,
            PushDelivery.Status.FAILED,
            failure_code="permanent_provider_error",
        )
        return PushDelivery.Status.FAILED

    _finish_push_delivery(
        delivery.pk,
        PushDelivery.Status.SENT,
        message_id=message_id,
    )
    return PushDelivery.Status.SENT


@shared_task(name="notifications.recover_queued_push_deliveries")
def recover_queued_push_deliveries():
    """Recover queued publications and worker claims abandoned before send."""
    stale_before = timezone.now() - timedelta(minutes=10)
    PushDelivery.all_objects.filter(
        status=PushDelivery.Status.PROCESSING,
        processing_started_at__lt=stale_before,
    ).update(
        status=PushDelivery.Status.QUEUED,
        processing_started_at=None,
        failure_code="stale_worker_claim",
        updated_at=timezone.now(),
    )
    delivery_ids = list(
        PushDelivery.objects.filter(status=PushDelivery.Status.QUEUED)
        .values_list("pk", flat=True)
    )
    for delivery_id in delivery_ids:
        deliver_push_notification.delay(str(delivery_id))
    return len(delivery_ids)


def _project_completion_reminder(project, today):
    expected_date = project.expected_completion_date
    if expected_date is None:
        return None

    days_remaining = (expected_date - today).days
    if days_remaining not in PROJECT_COMPLETION_MILESTONES and days_remaining >= 0:
        return None

    if days_remaining > 0:
        return {
            "milestone": f"{days_remaining}-days",
            "title": "تذكير بموعد اكتمال المشروع",
            "body": (
                f"يقترب مشروع {project.name} من تاريخ اكتماله المتوقع. "
                f"متبقٍ {days_remaining} يومًا."
            ),
            "tone": (
                Notification.Tone.INFO
                if days_remaining == 30
                else Notification.Tone.WARNING
            ),
        }
    if days_remaining == 0:
        return {
            "milestone": "due",
            "title": "تذكير بموعد اكتمال المشروع",
            "body": (
                f"وصل مشروع {project.name} إلى تاريخ اكتماله المتوقع اليوم."
            ),
            "tone": Notification.Tone.CRITICAL,
        }

    days_overdue = abs(days_remaining)
    return {
        "milestone": "overdue",
        "title": "مشروع متأخر",
        "body": (
            f"تجاوز مشروع {project.name} تاريخ اكتماله المتوقع ولم يكتمل بعد. "
            f"مدة التأخير {days_overdue} يومًا."
        ),
        "tone": Notification.Tone.CRITICAL,
    }


def _notify_project_completion_recipients(project, reminder, super_admins):
    managers = list(
        User.objects.filter(
            status=User.STATUS_ACTIVE,
            role__name=Role.CONSTRUCTION_MANAGER,
            project_assignments__project=project,
            project_assignments__is_active=True,
        ).distinct()
    )
    deduplication_key = (
        f"project-completion:{project.pk}:{reminder['milestone']}"
    )
    common = {
        "title": reminder["title"],
        "body": reminder["body"],
        "category": Notification.Category.PROJECT,
        "tone": reminder["tone"],
        "source": project,
        "deduplication_key": deduplication_key,
    }
    notify_users(
        super_admins,
        href=f"/admin/projects/{project.pk}",
        **common,
    )
    notify_users(
        managers,
        href=f"/construction/projects/{project.pk}",
        **common,
    )
    return len({user.pk for user in [*super_admins, *managers]})


@shared_task(
    name="notifications.notify_project_completion_reminders",
    autoretry_for=TRANSIENT_TASK_ERRORS,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=5,
    acks_late=True,
)
def notify_project_completion_reminders():
    """Send each project expected-completion milestone once per recipient."""
    today = timezone.localdate()
    milestone_dates = [today + timedelta(days=days) for days in (30, 14, 7, 0)]
    projects = (
        Project.objects.filter(
            status__in=[Project.Status.PLANNING, Project.Status.IN_PROGRESS]
        )
        .filter(
            Q(expected_completion_date__in=milestone_dates)
            | Q(expected_completion_date__lt=today)
        )
        .order_by("id")
    )
    super_admins = list(
        User.objects.filter(
            status=User.STATUS_ACTIVE,
            role__name=Role.SUPER_ADMIN,
        )
    )
    targeted = 0
    for project in projects.iterator():
        try:
            reminder = _project_completion_reminder(project, today)
            if reminder is not None:
                targeted += _notify_project_completion_recipients(
                    project,
                    reminder,
                    super_admins,
                )
        except Exception:
            logger.exception(
                "Project completion reminder failed for project %s",
                project.pk,
            )
    return targeted


@shared_task(
    name="notifications.notify_overdue_work_orders",
    autoretry_for=TRANSIENT_TASK_ERRORS,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=5,
    acks_late=True,
)
def notify_overdue_work_orders():
    """Send one database-backed overdue reminder per order and recipient/day."""
    if not setting_enabled("notify.overdueWorkOrders"):
        return 0
    today = timezone.localdate()
    orders = MaintenanceOrder.objects.filter(
        expected_execution_date__lt=today,
        status__in=[
            MaintenanceOrder.Status.OPEN,
            MaintenanceOrder.Status.ASSIGNED,
            MaintenanceOrder.Status.IN_PROGRESS,
        ],
    ).select_related("asset__facility", "assigned_to")
    sent = 0
    for order in orders.iterator():
        users = list(
            assignment.user
            for assignment in FacilityAssignment.objects.filter(
                facility=order.asset.facility,
                role_type=FacilityAssignment.RoleType.OPERATIONS_MANAGER,
                is_active=True,
                user__status="active",
            ).select_related("user")
        )
        if order.assigned_to and order.assigned_to not in users:
            users.append(order.assigned_to)
        already_notified = set(
            Notification.objects.filter(
                recipient__in=users,
                source_type=order._meta.label_lower,
                source_id=order.pk,
                title="Overdue maintenance order",
                created_at__date=today,
            ).values_list("recipient_id", flat=True)
        )
        eligible = [user for user in users if user.pk not in already_notified]
        notify_users(
            eligible,
            title="Overdue maintenance order",
            body=f"Maintenance order {order.reference} is overdue.",
            category=Notification.Category.MAINTENANCE,
            tone=Notification.Tone.WARNING,
            href=f"/operations/work-orders/{order.pk}",
            source=order,
            preference_field="overdue_work_orders",
            deduplication_key=f"overdue-order:{order.pk}:{today.isoformat()}",
        )
        sent += len(eligible)
    return sent


@shared_task(
    name="notifications.notify_critical_security_alerts",
    autoretry_for=TRANSIENT_TASK_ERRORS,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=5,
    acks_late=True,
)
def notify_critical_security_alerts():
    """Notify scoped security staff and administrators once per critical alert."""
    if not setting_enabled("notify.criticalAlerts"):
        return 0
    alerts = SecurityAlert.objects.filter(
        status=SecurityAlert.Status.NEW,
        severity_level=SecurityAlert.Severity.CRITICAL,
    ).select_related("facility")
    sent = 0
    for alert in alerts.iterator():
        if setting_enabled("workflow.autoIncident", default=False):
            actor = alert.created_by if alert.created_by and alert.created_by.is_active else User.objects.filter(
                status=User.STATUS_ACTIVE,
                role__name=Role.SUPER_ADMIN,
            ).first()
            if actor:
                try:
                    review_security_alert(
                        alert_id=alert.pk,
                        actor=actor,
                        notes="Automatically reviewed by the critical-alert policy.",
                    )
                    convert_alert_to_incident(
                        alert_id=alert.pk,
                        incident_type=alert.alert_type,
                        description=f"Automatically created from critical alert at {alert.location}.",
                        actor=actor,
                    )
                except ValidationError:
                    logger.warning(
                        "Automatic incident creation was rejected for alert %s",
                        alert.pk,
                        exc_info=True,
                    )
                except TRANSIENT_TASK_ERRORS:
                    raise
                except Exception:
                    logger.exception("Automatic incident creation failed for alert %s", alert.pk)
        users = list(User.objects.filter(pk__in=security_alert_recipient_ids(alert)))
        notified = set(
            Notification.objects.filter(
                recipient__in=users,
                source_type=alert._meta.label_lower,
                source_id=alert.pk,
            ).values_list("recipient_id", flat=True)
        )
        eligible = [user for user in users if user.pk not in notified]
        notify_users(
            eligible,
            title="تنبيه أمني حرج جديد",
            body=f"تم استلام تنبيه {alert.get_alert_type_display()} حرج في {alert.location}.",
            category=Notification.Category.SECURITY,
            tone=Notification.Tone.CRITICAL,
            href=f"/security/alerts/{alert.pk}",
            source=alert,
            preference_field="critical_alerts",
            deduplication_key=f"security-alert:{alert.pk}",
        )
        sent += len(eligible)
    return sent
