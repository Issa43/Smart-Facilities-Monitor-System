from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.assets.models import Asset
from apps.facilities.models import Facility, FacilityAssignment
from apps.maintenance.models import MaintenanceOrder
from apps.notifications.models import Notification, NotificationPreference
from apps.notifications.tasks import (
    _project_completion_reminder,
    notify_critical_security_alerts,
    notify_overdue_work_orders,
    notify_project_completion_reminders,
)
from apps.projects.models import Project, ProjectAssignment
from apps.security.models import SecurityAlert
from apps.users.models import User


PROJECT_REMINDER_TODAY = date(2026, 9, 1)


def create_user(*, role, suffix):
    return User.objects.create_user(
        email=f"{suffix}@sflms.test",
        username=suffix,
        full_name=suffix.replace("-", " ").title(),
        password="StrongPass123!",
        role=role,
    )


def create_facility(*, actor, name):
    return Facility.objects.create(
        name=name,
        type=Facility.Type.COMMERCIAL,
        location="Cairo",
        operation_start_date=date.today(),
        created_by=actor,
    )


def create_project(
    *,
    actor,
    name,
    days_until_completion,
    status=Project.Status.IN_PROGRESS,
    facility=None,
):
    terminal = status in {Project.Status.COMPLETED, Project.Status.OPERATIONAL}
    return Project.objects.create(
        name=name,
        facility=facility,
        facility_type=Project.FacilityType.COMMERCIAL,
        description="Project completion reminder test",
        location="Cairo",
        start_date=PROJECT_REMINDER_TODAY - timedelta(days=90),
        expected_completion_date=(
            PROJECT_REMINDER_TODAY + timedelta(days=days_until_completion)
        ),
        actual_completion_date=PROJECT_REMINDER_TODAY if terminal else None,
        status=status,
        created_by=actor,
    )


def assign_project(project, user, actor, role_type=ProjectAssignment.RoleType.PRIMARY_MANAGER):
    return ProjectAssignment.objects.create(
        project=project,
        user=user,
        role_type=role_type,
        created_by=actor,
    )


def run_project_reminders(django_capture_on_commit_callbacks):
    with patch(
        "apps.notifications.tasks.timezone.localdate",
        return_value=PROJECT_REMINDER_TODAY,
    ):
        with django_capture_on_commit_callbacks(execute=True):
            return notify_project_completion_reminders.run()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("days_remaining", "milestone", "expected_text", "tone"),
    [
        (30, "30-days", "متبقٍ 30 يومًا", Notification.Tone.INFO),
        (14, "14-days", "متبقٍ 14 يومًا", Notification.Tone.WARNING),
        (7, "7-days", "متبقٍ 7 يومًا", Notification.Tone.WARNING),
        (0, "due", "تاريخ اكتماله المتوقع اليوم", Notification.Tone.CRITICAL),
        (-3, "overdue", "مدة التأخير 3 يومًا", Notification.Tone.CRITICAL),
    ],
)
def test_project_completion_milestones_are_scoped_linked_and_idempotent(
    days_remaining,
    milestone,
    expected_text,
    tone,
    role_construction_manager,
    super_admin_user,
    django_capture_on_commit_callbacks,
):
    manager = create_user(role=role_construction_manager, suffix=f"manager-{milestone}")
    project = create_project(
        actor=super_admin_user,
        name=f"Milestone {milestone}",
        days_until_completion=days_remaining,
    )
    assign_project(project, manager, super_admin_user)

    run_project_reminders(django_capture_on_commit_callbacks)
    run_project_reminders(django_capture_on_commit_callbacks)

    notifications = Notification.objects.filter(source_id=project.pk)
    assert notifications.count() == 2
    assert set(notifications.values_list("recipient_id", flat=True)) == {
        manager.pk,
        super_admin_user.pk,
    }
    assert all(expected_text in body for body in notifications.values_list("body", flat=True))
    assert set(notifications.values_list("tone", flat=True)) == {tone}
    assert set(notifications.values_list("category", flat=True)) == {
        Notification.Category.PROJECT
    }
    assert set(notifications.values_list("href", flat=True)) == {
        f"/admin/projects/{project.pk}",
        f"/construction/projects/{project.pk}",
    }
    assert all(
        key.endswith(f"project-completion:{project.pk}:{milestone}")
        for key in notifications.values_list("deduplication_key", flat=True)
    )


@pytest.mark.django_db
def test_project_completion_reminders_exclude_terminal_and_archived_projects(
    super_admin_user,
    django_capture_on_commit_callbacks,
):
    facility = create_facility(actor=super_admin_user, name="Operational Facility")
    completed_projects = [
        create_project(
            actor=super_admin_user,
            name=f"Completed Project {days_remaining}",
            days_until_completion=days_remaining,
            status=Project.Status.COMPLETED,
        )
        for days_remaining in (30, 14, 7, 0, -1)
    ]
    operational = create_project(
        actor=super_admin_user,
        name="Operational Project",
        days_until_completion=14,
        status=Project.Status.OPERATIONAL,
        facility=facility,
    )
    archived = create_project(
        actor=super_admin_user,
        name="Archived Project",
        days_until_completion=-2,
    )
    archived.soft_delete()

    run_project_reminders(django_capture_on_commit_callbacks)

    assert not Notification.objects.filter(
        source_id__in=[
            *(project.pk for project in completed_projects),
            operational.pk,
            archived.pk,
        ]
    ).exists()


@pytest.mark.django_db
def test_project_completion_recipients_use_active_assignments_and_roles(
    role_construction_manager,
    role_operations_manager,
    role_security_officer,
    super_admin_user,
    django_capture_on_commit_callbacks,
):
    manager_one = create_user(role=role_construction_manager, suffix="assigned-manager-one")
    manager_two = create_user(role=role_construction_manager, suffix="assigned-manager-two")
    inactive_assignment = create_user(
        role=role_construction_manager,
        suffix="inactive-assignment-manager",
    )
    unassigned_manager = create_user(
        role=role_construction_manager,
        suffix="unassigned-manager",
    )
    operations_manager = create_user(role=role_operations_manager, suffix="operations-recipient")
    security_officer = create_user(role=role_security_officer, suffix="security-recipient")
    project = create_project(
        actor=super_admin_user,
        name="Recipient Scope",
        days_until_completion=7,
    )
    assign_project(project, manager_one, super_admin_user)
    assign_project(
        project,
        manager_two,
        super_admin_user,
        ProjectAssignment.RoleType.ENGINEER,
    )
    assignment = assign_project(project, inactive_assignment, super_admin_user)
    assignment.soft_delete()

    run_project_reminders(django_capture_on_commit_callbacks)

    recipients = set(
        Notification.objects.filter(source_id=project.pk).values_list(
            "recipient_id", flat=True
        )
    )
    assert recipients == {super_admin_user.pk, manager_one.pk, manager_two.pk}
    assert unassigned_manager.pk not in recipients
    assert operations_manager.pk not in recipients
    assert security_officer.pk not in recipients
    assert inactive_assignment.pk not in recipients


@pytest.mark.django_db
def test_project_completion_reschedule_uses_only_the_current_expected_date(
    role_construction_manager,
    super_admin_user,
    django_capture_on_commit_callbacks,
):
    manager = create_user(role=role_construction_manager, suffix="rescheduled-manager")
    project = create_project(
        actor=super_admin_user,
        name="Rescheduled Project",
        days_until_completion=31,
    )
    assign_project(project, manager, super_admin_user)

    run_project_reminders(django_capture_on_commit_callbacks)
    assert not Notification.objects.filter(source_id=project.pk).exists()

    project.expected_completion_date = PROJECT_REMINDER_TODAY + timedelta(days=14)
    project.save(update_fields=["expected_completion_date", "updated_at"])
    run_project_reminders(django_capture_on_commit_callbacks)

    notifications = Notification.objects.filter(source_id=project.pk)
    assert notifications.count() == 2
    assert all("متبقٍ 14 يومًا" in item.body for item in notifications)
    assert all("14-days" in item.deduplication_key for item in notifications)


@pytest.mark.django_db
def test_multiple_projects_are_independent_and_one_failure_does_not_stop_others(
    role_construction_manager,
    super_admin_user,
    django_capture_on_commit_callbacks,
):
    manager = create_user(role=role_construction_manager, suffix="isolation-manager")
    failing = create_project(
        actor=super_admin_user,
        name="Failing Reminder Project",
        days_until_completion=30,
    )
    healthy = create_project(
        actor=super_admin_user,
        name="Healthy Reminder Project",
        days_until_completion=30,
    )
    assign_project(failing, manager, super_admin_user)
    assign_project(healthy, manager, super_admin_user)

    from apps.notifications import tasks

    original = tasks._notify_project_completion_recipients

    def fail_one_project(project, reminder, super_admins):
        if project.pk == failing.pk:
            raise RuntimeError("isolated test failure")
        return original(project, reminder, super_admins)

    with patch.object(
        tasks,
        "_notify_project_completion_recipients",
        side_effect=fail_one_project,
    ):
        run_project_reminders(django_capture_on_commit_callbacks)

    assert not Notification.objects.filter(source_id=failing.pk).exists()
    assert Notification.objects.filter(source_id=healthy.pk).count() == 2


def test_project_completion_evaluator_handles_missing_date_defensively():
    project = SimpleNamespace(expected_completion_date=None, name="Missing Date")
    assert _project_completion_reminder(project, PROJECT_REMINDER_TODAY) is None


@pytest.mark.django_db
def test_overdue_task_is_daily_idempotent_and_honours_preferences(
    role_operations_manager,
    super_admin_user,
    django_capture_on_commit_callbacks,
):
    manager = create_user(role=role_operations_manager, suffix="overdue-manager")
    opted_out = create_user(role=role_operations_manager, suffix="overdue-opt-out")
    facility = create_facility(actor=super_admin_user, name="Overdue Facility")
    for user in (manager, opted_out):
        FacilityAssignment.objects.create(
            facility=facility,
            user=user,
            role_type=FacilityAssignment.RoleType.OPERATIONS_MANAGER,
            created_by=super_admin_user,
        )
    NotificationPreference.objects.create(
        user=opted_out,
        overdue_work_orders=False,
        created_by=opted_out,
    )
    asset = Asset.objects.create(
        facility=facility,
        name="Pump",
        asset_type="Mechanical",
        category="pump",
        serial_number="TASK-OVERDUE-1",
        manufacturer="Maker",
        model="P1",
        location_inside_facility="Plant room",
        installation_date=date.today(),
        created_by=manager,
    )
    order = MaintenanceOrder.objects.create(
        asset=asset,
        type=MaintenanceOrder.Type.CORRECTIVE,
        priority=MaintenanceOrder.Priority.HIGH,
        description="Repair overdue pump",
        reason="Leak",
        expected_execution_date=date.today() - timedelta(days=1),
        assigned_to=manager,
        status=MaintenanceOrder.Status.ASSIGNED,
        created_by=manager,
    )

    with django_capture_on_commit_callbacks(execute=True):
        notify_overdue_work_orders.run()
    with django_capture_on_commit_callbacks(execute=True):
        notify_overdue_work_orders.run()

    notifications = Notification.objects.filter(source_id=order.pk)
    assert notifications.count() == 1
    notification = notifications.get()
    assert notification.recipient == manager
    assert notification.href == f"/operations/work-orders/{order.pk}"
    assert notification.deduplication_key


@pytest.mark.django_db
def test_critical_alert_task_is_idempotent_scoped_and_linked(
    role_security_officer,
    super_admin_user,
    django_capture_on_commit_callbacks,
):
    officer = create_user(role=role_security_officer, suffix="critical-officer")
    facility = create_facility(actor=super_admin_user, name="Critical Facility")
    FacilityAssignment.objects.create(
        facility=facility,
        user=officer,
        role_type=FacilityAssignment.RoleType.SECURITY_OFFICER,
        created_by=super_admin_user,
    )
    alert = SecurityAlert.objects.create(
        facility=facility,
        alert_type=SecurityAlert.AlertType.FIRE,
        location="Lobby",
        severity_level=SecurityAlert.Severity.CRITICAL,
        source=SecurityAlert.Source.MANUAL,
        created_by=officer,
    )

    with django_capture_on_commit_callbacks(execute=True):
        notify_critical_security_alerts.run()
    with django_capture_on_commit_callbacks(execute=True):
        notify_critical_security_alerts.run()

    notifications = Notification.objects.filter(source_id=alert.pk)
    assert notifications.filter(recipient=officer).count() == 1
    assert notifications.filter(recipient=super_admin_user).count() == 1
    assert set(notifications.values_list("href", flat=True)) == {
        f"/security/alerts/{alert.pk}"
    }
    assert all(notifications.values_list("deduplication_key", flat=True))


def test_scheduled_tasks_have_transient_retry_policy(settings):
    assert notify_overdue_work_orders.max_retries == 5
    assert notify_critical_security_alerts.max_retries == 5
    assert notify_project_completion_reminders.max_retries == 5
    assert notify_overdue_work_orders.acks_late is True
    assert notify_critical_security_alerts.acks_late is True
    assert notify_project_completion_reminders.acks_late is True
    scheduled = {entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()}
    assert "notifications.notify_overdue_work_orders" in scheduled
    assert "notifications.notify_critical_security_alerts" in scheduled
    assert "notifications.notify_project_completion_reminders" in scheduled
