from celery import shared_task

from .services import generate_report


@shared_task(name="reports.generate_report")
def generate_report_task(report_id):
    """Run the approved report generator outside the request/response cycle."""
    report = generate_report(report_id=report_id)
    return str(report.pk)
