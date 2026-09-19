from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.projects.models import PhaseProgressLog, Project, ProjectPhase


def create_project(*, actor, name, status, expected_date):
    return Project.objects.create(
        name=name,
        facility_type=Project.FacilityType.COMMERCIAL,
        location="Cairo",
        start_date=expected_date - timedelta(days=90),
        expected_completion_date=expected_date,
        actual_completion_date=(
            expected_date if status == Project.Status.COMPLETED else None
        ),
        status=status,
        created_by=actor,
    )


def create_phase(*, project, actor, sequence, progress):
    return ProjectPhase.objects.create(
        project=project,
        name=f"Phase {sequence}",
        sequence_number=sequence,
        start_date=project.start_date,
        expected_completion_date=project.expected_completion_date,
        current_progress=Decimal(str(progress)),
        status=ProjectPhase.Status.IN_PROGRESS,
        created_by=actor,
    )


@pytest.mark.django_db
def test_admin_analytics_uses_project_weighting_active_delay_rules_and_six_month_trend(
    authenticated_client,
    super_admin_user,
):
    today = timezone.localdate()
    completed = create_project(
        actor=super_admin_user,
        name="Completed",
        status=Project.Status.COMPLETED,
        expected_date=today - timedelta(days=20),
    )
    planning = create_project(
        actor=super_admin_user,
        name="Delayed planning",
        status=Project.Status.PLANNING,
        expected_date=today - timedelta(days=1),
    )
    active = create_project(
        actor=super_admin_user,
        name="Active future",
        status=Project.Status.IN_PROGRESS,
        expected_date=today + timedelta(days=30),
    )
    archived = create_project(
        actor=super_admin_user,
        name="Archived",
        status=Project.Status.IN_PROGRESS,
        expected_date=today - timedelta(days=1),
    )
    archived.soft_delete()

    first = create_phase(project=completed, actor=super_admin_user, sequence=1, progress=100)
    create_phase(project=completed, actor=super_admin_user, sequence=2, progress=100)
    create_phase(project=planning, actor=super_admin_user, sequence=1, progress=0)
    # The active project has no phase, so its real calculated project progress is zero.

    recent = PhaseProgressLog.objects.create(
        phase=first,
        progress_percentage=Decimal("100.00"),
        work_completed="Recent progress",
        created_by=super_admin_user,
    )
    old = PhaseProgressLog.objects.create(
        phase=first,
        progress_percentage=Decimal("25.00"),
        work_completed="Old progress",
        created_by=super_admin_user,
    )
    PhaseProgressLog.all_objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=220)
    )

    response = authenticated_client.get("/api/v1/analytics/admin/")

    assert response.status_code == 200
    assert response.data["total_projects"] == 3
    assert response.data["active_projects"] == 2
    assert response.data["delayed_projects"] == 1
    assert response.data["overall_progress"] == 33.33
    trend_values = [row["value"] for row in response.data["progress_trend"]]
    assert 100.0 in trend_values
    assert 25.0 not in trend_values
    assert recent.created_at is not None


@pytest.mark.django_db
def test_admin_analytics_empty_database_returns_honest_zeroes(authenticated_client):
    response = authenticated_client.get("/api/v1/analytics/admin/")

    assert response.status_code == 200
    assert response.data["total_projects"] == 0
    assert response.data["overall_progress"] == 0
    assert response.data["delayed_projects"] == 0
    assert response.data["progress_trend"] == []
    assert response.data["projects_by_status"] == []
    assert response.data["assets_by_status"] == []
