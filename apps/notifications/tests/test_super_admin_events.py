from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.facilities.models import Facility
from apps.materials.models import Material
from apps.notifications.models import Notification
from apps.projects.models import Project, ProjectAssignment
from apps.security.models import Incident
from apps.security.services import create_manual_incident
from apps.users.models import Permission, Role, User


@pytest.mark.django_db
def test_material_request_creation_notifies_active_super_admin_once_without_mirroring_api_audit(
    api_client,
    super_admin_user,
    construction_manager_user,
    role_construction_manager,
    django_capture_on_commit_callbacks,
):
    Permission.objects.get_or_create(
        role=role_construction_manager,
        permission_name="material.request",
    )
    today = timezone.localdate()
    project = Project.objects.create(
        name="Notification Project",
        facility_type=Project.FacilityType.COMMERCIAL,
        location="Cairo",
        start_date=today,
        expected_completion_date=today + timedelta(days=30),
        status=Project.Status.IN_PROGRESS,
        created_by=super_admin_user,
    )
    ProjectAssignment.objects.create(
        project=project,
        user=construction_manager_user,
        role_type=ProjectAssignment.RoleType.PRIMARY_MANAGER,
        created_by=super_admin_user,
    )
    material = Material.objects.create(
        project=project,
        name="Cement",
        unit=Material.Unit.BAG,
        quantity_required=Decimal("20.000"),
        quantity_used=Decimal("0.000"),
        quantity_remaining=Decimal("20.000"),
        min_stock_threshold=Decimal("5.000"),
        created_by=construction_manager_user,
    )
    inactive_admin = User.objects.create_user(
        email="inactive-admin@sflms.test",
        username="inactive-admin",
        full_name="Inactive Admin",
        password="StrongPass123!",
        role=super_admin_user.role,
        status=User.STATUS_INACTIVE,
    )
    api_client.force_authenticate(construction_manager_user)

    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(
            "/api/v1/construction/material-requests/",
            {
                "project": str(project.pk),
                "material": str(material.pk),
                "quantity_requested": "3.000",
                "reason": "Required for concrete works",
                "priority": "urgent",
            },
            format="json",
        )

    assert response.status_code == 201
    notifications = Notification.objects.filter(source_id=response.data["id"])
    assert notifications.count() == 1
    notification = notifications.get()
    assert notification.recipient == super_admin_user
    assert notification.title == "طلب توريد مواد جديد بانتظار اعتمادك"
    assert project.name in notification.body
    assert notification.href == "/admin/material-requests"
    assert notification.deduplication_key
    assert not notifications.filter(recipient=inactive_admin).exists()
    # The immutable technical audit envelope remains audit data, not a notification source.
    assert Notification.objects.count() == 1
    assert AuditLog.objects.filter(action="api.post").exists()


@pytest.mark.django_db
def test_incident_creation_notifies_assignee_and_active_super_admin_with_one_domain_event_each(
    super_admin_user,
    role_security_officer,
    django_capture_on_commit_callbacks,
):
    officer = User.objects.create_user(
        email="incident-officer@sflms.test",
        username="incident-officer",
        full_name="Incident Officer",
        password="StrongPass123!",
        role=role_security_officer,
    )
    facility = Facility.objects.create(
        name="Security Facility",
        type=Facility.Type.COMMERCIAL,
        location="Cairo",
        created_by=super_admin_user,
    )

    with django_capture_on_commit_callbacks(execute=True):
        incident = create_manual_incident(
            facility_id=facility.pk,
            actor=officer,
            incident_type="Unauthorized access",
            description="Access event under review",
            location="North gate",
            severity_level=Incident.Severity.HIGH,
            assigned_to=officer,
        )

    notifications = Notification.objects.filter(source_id=incident.pk)
    assert notifications.count() == 2
    assert set(notifications.values_list("recipient_id", flat=True)) == {
        super_admin_user.pk,
        officer.pk,
    }
    assert set(notifications.values_list("title", flat=True)) == {
        "تم تسجيل حادث أمني جديد"
    }
    assert set(notifications.values_list("href", flat=True)) == {
        f"/security/incidents/{incident.pk}"
    }
    assert all(notifications.values_list("deduplication_key", flat=True))
