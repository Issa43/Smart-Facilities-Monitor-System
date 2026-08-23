from celery import shared_task

from apps.notifications.models import Notification
from apps.notifications.services import notify_user

from .models import Report
from .services import generate_report


@shared_task(name="reports.generate_report")
def generate_report_task(report_id):
    """Run the approved report generator outside the request/response cycle."""
    try:
        report = generate_report(report_id=report_id)
    except Exception:
        report = Report.all_objects.select_related("created_by").filter(pk=report_id).first()
        if report is not None:
            notify_user(
                report.created_by,
                title="Report generation failed",
                body=f"The requested report '{report.type}' could not be generated.",
                category=Notification.Category.SYSTEM,
                tone=Notification.Tone.CRITICAL,
                source=report,
            )
        raise
    notify_user(
        report.created_by,
        title="Report ready",
        body=f"The requested report '{report.type}' is ready to download.",
        category=Notification.Category.SYSTEM,
        tone=Notification.Tone.SUCCESS,
        source=report,
    )
    return str(report.pk)
