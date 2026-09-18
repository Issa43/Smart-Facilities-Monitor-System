from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.db import OperationalError

from apps.notifications.models import Notification
from apps.reports.models import Report
from apps.reports.services import create_report_request
from apps.reports.tasks import generate_report_task
from apps.users.models import User


def create_report(*, role):
    actor = User.objects.create_user(
        email="task-report@sflms.test",
        username="task-report",
        full_name="Task Report",
        password="StrongPass123!",
        role=role,
    )
    return create_report_request(
        report_type="Task report",
        module=Report.Module.CONSTRUCTION,
        report_format=Report.Format.PDF,
        parameters={"date_from": "2026-01-01"},
        actor=actor,
    )


@pytest.mark.django_db
def test_transient_report_failure_requeues_with_backoff(role_construction_manager):
    report = create_report(role=role_construction_manager)

    def transient_failure(report_id):
        current = Report.objects.get(pk=report_id)
        current.status = Report.Status.FAILED
        current.parameters = {
            **current.parameters,
            "_generation_error": "storage unavailable",
        }
        current.save(update_fields=["status", "parameters", "updated_at"])
        raise OperationalError("storage unavailable")

    with (
        patch("apps.reports.tasks.generate_report", side_effect=transient_failure),
        patch.object(generate_report_task, "retry", side_effect=RuntimeError("retry scheduled")) as retry,
        pytest.raises(RuntimeError, match="retry scheduled"),
    ):
        generate_report_task.run(str(report.pk))

    report.refresh_from_db()
    assert report.status == Report.Status.QUEUED
    assert "_generation_error" not in report.parameters
    retry.assert_called_once()
    assert retry.call_args.kwargs["countdown"] == 2
    assert isinstance(retry.call_args.kwargs["exc"], OperationalError)


@pytest.mark.django_db
def test_domain_validation_failure_does_not_retry(
    role_construction_manager,
    django_capture_on_commit_callbacks,
):
    report = create_report(role=role_construction_manager)
    with (
        patch(
            "apps.reports.tasks.generate_report",
            side_effect=ValidationError({"configuration": "unsupported"}),
        ),
        patch.object(generate_report_task, "retry") as retry,
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(ValidationError),
    ):
        generate_report_task.run(str(report.pk))

    retry.assert_not_called()
    notification = Notification.objects.get(
        recipient=report.created_by,
        title="تعذّر إنشاء التقرير",
    )
    assert notification.href == "/construction/reports"
    assert notification.deduplication_key
