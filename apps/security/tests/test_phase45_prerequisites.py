from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError

from apps.attachments.access import (
    ProtectedAttachmentAccessDenied,
    ProtectedAttachmentNotFound,
    authorize_attachment_download,
    authorize_protected_file_download,
)
from apps.attachments.registry import AttachmentEntityRegistry
from apps.facilities.models import Facility, FacilityAssignment
from apps.security.models import Incident, SecurityAlert
from apps.security.services import (
    convert_alert_to_incident,
    create_manual_incident,
    record_incident_action,
)
from apps.users.models import Role, User


def create_facility(*, created_by, name="Test Facility"):
    return Facility.objects.create(
        name=name,
        type=Facility.Type.COMMERCIAL,
        location="Test location",
        created_by=created_by,
    )


def create_security_officer(*, role, suffix):
    return User.objects.create_user(
        email=f"security-{suffix}@sflms.test",
        username=f"security-{suffix}",
        full_name=f"Security Officer {suffix}",
        password="StrongPass123!",
        role=role,
        status=User.STATUS_ACTIVE,
    )


@pytest.mark.django_db
class TestSecurityAlertCategories:
    @pytest.mark.parametrize(
        "alert_type",
        [
            SecurityAlert.AlertType.UNAUTHORIZED_PERSON,
            SecurityAlert.AlertType.EMERGENCY,
        ],
    )
    def test_approved_alert_category_is_persisted(
        self,
        alert_type,
        super_admin_user,
    ):
        facility = create_facility(created_by=super_admin_user)
        alert = SecurityAlert.objects.create(
            facility=facility,
            alert_type=alert_type,
            location="North entrance",
            severity_level=SecurityAlert.Severity.HIGH,
            source=SecurityAlert.Source.MANUAL,
            created_by=super_admin_user,
        )

        alert.refresh_from_db()
        assert alert.alert_type == alert_type


@pytest.mark.django_db
class TestManualIncidentService:
    def test_creates_open_incident_without_alert(
        self,
        role_security_officer,
        super_admin_user,
    ):
        officer = create_security_officer(
            role=role_security_officer,
            suffix="manual",
        )
        facility = create_facility(created_by=super_admin_user)

        incident = create_manual_incident(
            facility_id=facility.id,
            actor=officer,
            incident_type="Unauthorized access",
            description="A restricted door was opened.",
            location="North entrance",
            severity_level=Incident.Severity.HIGH,
            assigned_to=officer,
        )

        assert incident.alert_id is None
        assert incident.status == Incident.Status.OPEN
        assert incident.created_by == officer
        assert incident.assigned_to == officer

    def test_invalid_manual_incident_is_not_persisted(
        self,
        role_security_officer,
        super_admin_user,
    ):
        officer = create_security_officer(
            role=role_security_officer,
            suffix="invalid",
        )
        facility = create_facility(created_by=super_admin_user)

        with pytest.raises(ValidationError):
            create_manual_incident(
                facility_id=facility.id,
                actor=officer,
                incident_type="",
                description="Description",
                location="Lobby",
                severity_level=Incident.Severity.LOW,
            )

        assert not Incident.objects.filter(facility=facility).exists()

    def test_alert_conversion_still_uses_shared_creation_rules(
        self,
        role_security_officer,
        super_admin_user,
    ):
        officer = create_security_officer(
            role=role_security_officer,
            suffix="conversion",
        )
        facility = create_facility(created_by=super_admin_user)
        alert = SecurityAlert.objects.create(
            facility=facility,
            alert_type=SecurityAlert.AlertType.FIRE,
            location="Plant room",
            severity_level=SecurityAlert.Severity.CRITICAL,
            source=SecurityAlert.Source.SENSOR,
            status=SecurityAlert.Status.REVIEWED,
            reviewed_by=officer,
            created_by=officer,
        )

        incident = convert_alert_to_incident(
            alert_id=alert.id,
            actor=officer,
            incident_type="Fire response",
            description="Confirmed fire alarm.",
            assigned_to=officer,
        )

        assert incident.alert == alert
        assert incident.location == alert.location
        assert incident.severity_level == alert.severity_level
        alert.refresh_from_db()
        assert alert.status == SecurityAlert.Status.CONVERTED


@pytest.mark.django_db
class TestSecurityAttachmentAuthorization:
    def test_incident_and_action_registry_resolve_facility(
        self,
        role_security_officer,
        super_admin_user,
    ):
        officer = create_security_officer(
            role=role_security_officer,
            suffix="registry",
        )
        facility = create_facility(created_by=super_admin_user)
        incident = create_manual_incident(
            facility_id=facility.id,
            actor=officer,
            incident_type="Perimeter breach",
            description="Fence breach detected.",
            location="West perimeter",
            severity_level=Incident.Severity.HIGH,
        )
        action = record_incident_action(
            incident_id=incident.id,
            actor=officer,
            action_taken="Secured perimeter",
        )

        assert AttachmentEntityRegistry.resolve("incident", incident.id) == incident
        assert (
            AttachmentEntityRegistry.resolve_facility("incident", incident)
            == facility
        )
        assert AttachmentEntityRegistry.resolve("incident_action", action.id) == action
        assert (
            AttachmentEntityRegistry.resolve_facility("incident_action", action)
            == facility
        )

    def test_assigned_security_officer_can_access_incident_evidence(
        self,
        role_security_officer,
        super_admin_user,
    ):
        officer = create_security_officer(
            role=role_security_officer,
            suffix="assigned",
        )
        facility = create_facility(created_by=super_admin_user)
        FacilityAssignment.objects.create(
            facility=facility,
            user=officer,
            role_type=FacilityAssignment.RoleType.SECURITY_OFFICER,
            created_by=super_admin_user,
        )
        incident = create_manual_incident(
            facility_id=facility.id,
            actor=officer,
            incident_type="Smoke response",
            description="Smoke observed in corridor.",
            location="Level 2",
            severity_level=Incident.Severity.MEDIUM,
        )
        action = record_incident_action(
            incident_id=incident.id,
            actor=officer,
            action_taken="Evacuated affected area",
        )
        incident_attachment = SimpleNamespace(
            is_active=True,
            entity_type="incident",
            entity_id=incident.id,
        )
        action_attachment = SimpleNamespace(
            is_active=True,
            entity_type="incident_action",
            entity_id=action.id,
        )

        assert authorize_attachment_download(officer, incident_attachment) == incident
        assert authorize_attachment_download(officer, action_attachment) == action

    def test_unassigned_security_officer_cannot_access_incident_evidence(
        self,
        role_security_officer,
        super_admin_user,
    ):
        officer = create_security_officer(
            role=role_security_officer,
            suffix="unassigned",
        )
        facility = create_facility(created_by=super_admin_user)
        incident = create_manual_incident(
            facility_id=facility.id,
            actor=officer,
            incident_type="Emergency",
            description="Emergency response initiated.",
            location="Lobby",
            severity_level=Incident.Severity.CRITICAL,
        )
        attachment = SimpleNamespace(
            is_active=True,
            entity_type="incident",
            entity_id=incident.id,
        )

        with pytest.raises(ProtectedAttachmentNotFound):
            authorize_attachment_download(officer, attachment)

    def test_snapshot_requires_active_facility_assignment(
        self,
        role_security_officer,
        super_admin_user,
    ):
        officer = create_security_officer(
            role=role_security_officer,
            suffix="snapshot",
        )
        facility = create_facility(created_by=super_admin_user)
        assignment = FacilityAssignment.objects.create(
            facility=facility,
            user=officer,
            role_type=FacilityAssignment.RoleType.SECURITY_OFFICER,
            created_by=super_admin_user,
        )
        alert = SecurityAlert.objects.create(
            facility=facility,
            alert_type=SecurityAlert.AlertType.EMERGENCY,
            location="Lobby",
            severity_level=SecurityAlert.Severity.CRITICAL,
            source=SecurityAlert.Source.MANUAL,
            created_by=officer,
        )

        assert authorize_protected_file_download(officer, alert) == alert

        assignment.soft_delete()
        with pytest.raises(ProtectedAttachmentNotFound):
            authorize_protected_file_download(officer, alert)

        assert authorize_protected_file_download(super_admin_user, alert) == alert

    def test_non_security_role_is_denied_even_with_active_assignment(
        self,
        role_operations_manager,
        super_admin_user,
    ):
        manager = User.objects.create_user(
            email="operations-evidence@sflms.test",
            username="operations-evidence",
            full_name="Operations Manager",
            password="StrongPass123!",
            role=role_operations_manager,
        )
        facility = create_facility(created_by=super_admin_user)
        FacilityAssignment.objects.create(
            facility=facility,
            user=manager,
            role_type=FacilityAssignment.RoleType.OPERATIONS_MANAGER,
            created_by=super_admin_user,
        )
        alert = SecurityAlert.objects.create(
            facility=facility,
            alert_type=SecurityAlert.AlertType.INTRUSION,
            location="Loading dock",
            severity_level=SecurityAlert.Severity.HIGH,
            source=SecurityAlert.Source.MANUAL,
            created_by=super_admin_user,
        )

        with pytest.raises(ProtectedAttachmentAccessDenied):
            authorize_protected_file_download(manager, alert)
