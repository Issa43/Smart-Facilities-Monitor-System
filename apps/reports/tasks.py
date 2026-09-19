from celery import shared_task
from django.core.exceptions import ValidationError
from django.db import InterfaceError, OperationalError
import logging

from apps.notifications.models import Notification
from apps.notifications.services import notify_user

from .models import Report
from .services import generate_report, requeue_failed_report


logger = logging.getLogger(__name__)
TRANSIENT_TASK_ERRORS = (OperationalError, InterfaceError, OSError, ConnectionError, TimeoutError)


REPORT_HREF_BY_ROLE = {
    "super_admin": "/admin/reports",
    "construction_manager": "/construction/reports",
    "operations_manager": "/operations/reports",
    "security_officer": "/security/reports",
}


def _report_href(report):
    role = report.created_by.role.name if report.created_by.role_id else None
    return REPORT_HREF_BY_ROLE.get(role)


@shared_task(bind=True, name="reports.generate_report", max_retries=5, acks_late=True)
def generate_report_task(self, report_id):
    """Run the approved report generator outside the request/response cycle."""
    try:
        report = generate_report(report_id=report_id)
    except ValidationError:
        logger.warning("Report generation was rejected for report %s", report_id, exc_info=True)
        report = Report.all_objects.select_related("created_by__role").filter(pk=report_id).first()
        if report is not None:
            notify_user(
                report.created_by,
                title="تعذّر إنشاء التقرير",
                body=f"تعذّر إنشاء التقرير المطلوب «{report.type}».",
                category=Notification.Category.SYSTEM,
                tone=Notification.Tone.CRITICAL,
                href=_report_href(report),
                source=report,
                deduplication_key=f"report:{report.pk}:failed",
            )
        raise
    except TRANSIENT_TASK_ERRORS as exc:
        logger.warning(
            "Transient report generation failure for %s; retry %s of %s",
            report_id,
            self.request.retries + 1,
            self.max_retries,
            exc_info=True,
        )
        requeue_failed_report(report_id=report_id)
        raise self.retry(
            exc=exc,
            countdown=min(2 ** (self.request.retries + 1), 300),
        )
    except Exception:
        logger.exception("Permanent report generation failure for report %s", report_id)
        report = Report.all_objects.select_related("created_by__role").filter(pk=report_id).first()
        if report is not None:
            notify_user(
                report.created_by,
                title="تعذّر إنشاء التقرير",
                body=f"تعذّر إنشاء التقرير المطلوب «{report.type}».",
                category=Notification.Category.SYSTEM,
                tone=Notification.Tone.CRITICAL,
                href=_report_href(report),
                source=report,
                deduplication_key=f"report:{report.pk}:failed",
            )
        raise
    notify_user(
        report.created_by,
        title="التقرير جاهز للتنزيل",
        body=f"اكتمل إنشاء التقرير المطلوب «{report.type}» ويمكن تنزيله الآن.",
        category=Notification.Category.SYSTEM,
        tone=Notification.Tone.SUCCESS,
        href=_report_href(report),
        source=report,
        deduplication_key=f"report:{report.pk}:ready",
    )
    return str(report.pk)
