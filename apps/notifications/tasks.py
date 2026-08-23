from celery import shared_task
from django.utils import timezone
import logging

from apps.facilities.models import FacilityAssignment
from apps.maintenance.models import MaintenanceOrder
from apps.security.models import SecurityAlert
from apps.security.services import convert_alert_to_incident, review_security_alert
from apps.users.models import Role, User

from .models import Notification
from .services import notify_users, setting_enabled


logger = logging.getLogger(__name__)


@shared_task(name="notifications.notify_overdue_work_orders")
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
        )
        sent += len(eligible)
    return sent


@shared_task(name="notifications.notify_critical_security_alerts")
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
                except Exception:
                    logger.exception("Automatic incident creation failed for alert %s", alert.pk)
        users = User.objects.filter(
            status=User.STATUS_ACTIVE,
        ).filter(
            role__name=Role.SUPER_ADMIN
        ) | User.objects.filter(
            status=User.STATUS_ACTIVE,
            role__name=Role.SECURITY_OFFICER,
            facility_assignments__facility=alert.facility,
            facility_assignments__is_active=True,
        )
        users = list(users.distinct())
        notified = set(
            Notification.objects.filter(
                recipient__in=users,
                source_type=alert._meta.label_lower,
                source_id=alert.pk,
                title="Critical security alert",
            ).values_list("recipient_id", flat=True)
        )
        eligible = [user for user in users if user.pk not in notified]
        notify_users(
            eligible,
            title="Critical security alert",
            body=f"A critical {alert.get_alert_type_display()} alert was received at {alert.location}.",
            category=Notification.Category.SECURITY,
            tone=Notification.Tone.CRITICAL,
            href=f"/security/alerts/{alert.pk}",
            source=alert,
            preference_field="critical_alerts",
        )
        sent += len(eligible)
    return sent
