"""Durable manager notifications for project safety alerts.

Reuses the shared Notification system. Notifications are scheduled only after
the alert transaction commits and never influence alert state; a failure is
logged and cannot roll back the committed alert.
"""

import logging

from django.db import transaction

from apps.notifications.models import Notification
from apps.notifications.services import notify_users

from .policy import NOTIFY_SETTING_KEY
from .recipients import alert_recipient_groups


logger = logging.getLogger(__name__)

HAZARD_LABELS_AR = {
    "earthquake": "زلزال",
    "tropical_cyclone": "إعصار مداري",
    "flood": "فيضان",
    "volcano": "نشاط بركاني",
    "wildfire": "حريق غابات",
    "extreme_heat": "حرارة شديدة",
    "extreme_cold": "برودة شديدة",
    "heavy_snow": "تساقط كثيف للثلوج",
    "high_wind": "رياح شديدة",
    "heavy_rain": "أمطار غزيرة",
    "dust_storm": "عاصفة ترابية أو رملية",
}
ACTION_LABELS_AR = {
    "suspend_outdoor_work": "إيقاف الأعمال الخارجية مؤقتاً",
    "delay_shift": "تأجيل الوردية",
    "modify_working_hours": "تعديل ساعات العمل",
    "increase_precautions": "رفع إجراءات السلامة",
    "inspect_site": "فحص الموقع",
    "monitor": "المتابعة والمراقبة",
    "other": "إجراء آخر",
}
TONE_BY_SEVERITY = {
    "critical": Notification.Tone.CRITICAL,
    "high": Notification.Tone.WARNING,
    "medium": Notification.Tone.WARNING,
    "low": Notification.Tone.INFO,
}

KIND_CREATED = "created"
KIND_ESCALATED = "escalated"
KIND_WITHDRAWN = "withdrawn"


def deduplication_key(alert, *, kind, severity):
    if kind == KIND_WITHDRAWN:
        return f"safety-alert:{alert.pk}:withdrawn"
    return f"safety-alert:{alert.pk}:{severity}"


def notification_content(alert, *, kind, project_name, distance_km):
    hazard = HAZARD_LABELS_AR.get(alert.hazard_type, alert.hazard_type)
    action = ACTION_LABELS_AR.get(alert.recommended_action, alert.recommended_action)
    if kind == KIND_WITHDRAWN:
        return {
            "title": f"تحديث إنذار سلامة — {hazard}",
            "body": (
                f"أفاد مصدر البيانات بسحب حدث {hazard} المرتبط بمشروع {project_name}. "
                "يبقى الإنذار مفتوحاً حتى يغلقه المدير المسؤول."
            ),
            "tone": Notification.Tone.INFO,
        }
    prefix = "تصعيد إنذار سلامة" if kind == KIND_ESCALATED else "إنذار سلامة"
    return {
        "title": f"{prefix} — {hazard}",
        "body": (
            f"رُصد {hazard} على بعد {distance_km} كم من مشروع {project_name}. "
            f"الإجراء الموصى به: {action}. القرار النهائي للمدير المسؤول."
        ),
        "tone": TONE_BY_SEVERITY[alert.severity],
    }


def _deliver(alert_id, kind):
    from .models import ProjectSafetyAlert

    try:
        alert = ProjectSafetyAlert.objects.select_related("project").get(pk=alert_id)
        content = notification_content(
            alert,
            kind=kind,
            project_name=alert.project.name,
            distance_km=alert.distance_km,
        )
        key = deduplication_key(alert, kind=kind, severity=alert.severity)
        for group in alert_recipient_groups(alert):
            notify_users(
                group.users,
                title=content["title"],
                body=content["body"],
                category=Notification.Category.SAFETY,
                tone=content["tone"],
                href=group.href,
                source=alert,
                preference_field="critical_alerts",
                system_setting_key=NOTIFY_SETTING_KEY,
                deduplication_key=key,
            )
    except Exception:
        logger.exception("Safety alert notification failed.", extra={"alert_id": str(alert_id)})


def schedule_alert_notifications(alert, *, kind):
    """Queue notifications to run after the alert transaction commits."""

    alert_id = alert.pk
    transaction.on_commit(lambda: _deliver(alert_id, kind), robust=True)
