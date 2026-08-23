from celery import shared_task

from apps.notifications.models import Notification
from apps.notifications.services import notify_user

from .models import Report
from .services import generate_report


REPORT_HREF_BY_ROLE = {
    "super_admin": "/admin/reports",
    "construction_manager": "/construction/reports",
    "operations_manager": "/operations/reports",
    "security_officer": "/security/reports",
}


def _report_href(report):
    role = report.created_by.role.name if report.created_by.role_id else None
    return REPORT_HREF_BY_ROLE.get(role)


@shared_task(name="reports.generate_report")
def generate_report_task(report_id):
    """Run the approved report generator outside the request/response cycle."""
    try:
        report = generate_report(report_id=report_id)
    except Exception:
        report = Report.all_objects.select_related("created_by__role").filter(pk=report_id).first()
        if report is not None:
            notify_user(
                report.created_by,
                title="Report generation failed",
                body=f"The requested report '{report.type}' could not be generated.",
                category=Notification.Category.SYSTEM,
                tone=Notification.Tone.CRITICAL,
                href=_report_href(report),
                source=report,
            )
        raise
    notify_user(
        report.created_by,
        title="Report ready",
        body=f"The requested report '{report.type}' is ready to download.",
        category=Notification.Category.SYSTEM,
        tone=Notification.Tone.SUCCESS,
        href=_report_href(report),
        source=report,
    )
    return str(report.pk)
