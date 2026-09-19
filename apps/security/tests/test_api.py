from io import BytesIO
from unittest.mock import patch

import pytest
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status

from apps.attachments.models import Attachment
from apps.audit.models import AuditLog
from apps.facilities.models import Facility, FacilityAssignment
from apps.security.models import Incident, SecurityAlert
from apps.security.services import create_manual_incident
from apps.users.models import User


def create_facility(*, created_by, name):
    return Facility.objects.create(
        name=name,
        type=Facility.Type.COMMERCIAL,
        location=f"{name} location",
        created_by=created_by,
    )


def create_user(*, role, suffix):
    return User.objects.create_user(
        email=f"{suffix}@sflms.test",
        username=suffix,
        full_name=suffix.replace("-", " ").title(),
        password="StrongPass123!",
        role=role,
        status=User.STATUS_ACTIVE,
    )


def assign_facility(*, facility, user, role_type, created_by):
    return FacilityAssignment.objects.create(
        facility=facility,
        user=user,
        role_type=role_type,
        created_by=created_by,
    )


def create_alert(*, facility, created_by, alert_type=SecurityAlert.AlertType.FIRE):
    return SecurityAlert.objects.create(
        facility=facility,
        alert_type=alert_type,
        location="North entrance",
        severity_level=SecurityAlert.Severity.HIGH,
        source=SecurityAlert.Source.MANUAL,
        created_by=created_by,
    )


@pytest.mark.django_db
class TestSecurityOfficerAPI:
    def test_alert_queryset_is_assignment_scoped(
        self,
        api_client,
        role_security_officer,
        super_admin_user,
    ):
        officer = create_user(role=role_security_officer, suffix="security-scope")
        assigned = create_facility(created_by=super_admin_user, name="Assigned")
        hidden = create_facility(created_by=super_admin_user, name="Hidden")
        assign_facility(
            facility=assigned,
            user=officer,
            role_type=FacilityAssignment.RoleType.SECURITY_OFFICER,
            created_by=super_admin_user,
        )
        visible_alert = create_alert(facility=assigned, created_by=officer)
        hidden_alert = create_alert(facility=hidden, created_by=super_admin_user)
        api_client.force_authenticate(user=officer)

        response = api_client.get(reverse("api_v1:security-alert-list"))

        assert response.status_code == status.HTTP_200_OK
        assert [row["id"] for row in response.data["results"]] == [
            str(visible_alert.id)
        ]
        detail = api_client.get(
            reverse("api_v1:security-alert-detail", kwargs={"pk": hidden_alert.id})
        )
        assert detail.status_code == status.HTTP_404_NOT_FOUND

    def test_alert_review_dismiss_and_conversion_use_workflow_actions(
        self,
        api_client,
        role_security_officer,
        super_admin_user,
    ):
        officer = create_user(role=role_security_officer, suffix="security-alerts")
        facility = create_facility(created_by=super_admin_user, name="Alerts")
        assign_facility(
            facility=facility,
            user=officer,
            role_type=FacilityAssignment.RoleType.SECURITY_OFFICER,
            created_by=super_admin_user,
        )
        genuine = create_alert(facility=facility, created_by=officer)
        false_positive = create_alert(
            facility=facility,
            created_by=officer,
            alert_type=SecurityAlert.AlertType.MOTION,
        )
        api_client.force_authenticate(user=officer)

        review_url = reverse(
            "api_v1:security-alert-review",
            kwargs={"pk": genuine.id},
        )
        assert api_client.post(review_url, {"notes": "Confirmed"}).status_code == 200
        conversion = api_client.post(
            reverse(
                "api_v1:security-alert-convert-to-incident",
                kwargs={"pk": genuine.id},
            ),
            {
                "incident_type": "Fire response",
                "description": "Confirmed alert",
                "assigned_to": str(officer.id),
            },
            format="json",
        )
        assert conversion.status_code == status.HTTP_201_CREATED
        assert conversion.data["alert_id"] == str(genuine.id)

        assert api_client.post(
            reverse(
                "api_v1:security-alert-review",
                kwargs={"pk": false_positive.id},
            ),
            {},
            format="json",
        ).status_code == 200
        dismissal = api_client.post(
            reverse(
                "api_v1:security-alert-dismiss",
                kwargs={"pk": false_positive.id},
            ),
            {"reason": "No threat found"},
            format="json",
        )
        assert dismissal.status_code == status.HTTP_200_OK
        assert dismissal.data["status"] == SecurityAlert.Status.DISMISSED
        semantic_actions = list(
            AuditLog.objects.filter(
                action__in={
                    "security_alert.reviewed",
                    "security_alert.dismissed",
                    "security_alert.converted_to_incident",
                }
            )
            .order_by("created_at")
            .values_list("action", flat=True)
        )
        assert semantic_actions == [
            "security_alert.reviewed",
            "security_alert.converted_to_incident",
            "security_alert.reviewed",
            "security_alert.dismissed",
        ]
        for audit in AuditLog.objects.filter(action__in=semantic_actions):
            serialized = f"{audit.before!r}{audit.after!r}".lower()
            assert "snapshot" not in serialized
            assert "token" not in serialized
            assert "secret" not in serialized

    def test_manual_incident_actions_transfer_and_close(
        self,
        api_client,
        role_security_officer,
        role_operations_manager,
        super_admin_user,
    ):
        officer = create_user(role=role_security_officer, suffix="security-incident")
        operations_manager = create_user(
            role=role_operations_manager,
            suffix="operations-transfer",
        )
        facility = create_facility(created_by=super_admin_user, name="Incidents")
        assign_facility(
            facility=facility,
            user=officer,
            role_type=FacilityAssignment.RoleType.SECURITY_OFFICER,
            created_by=super_admin_user,
        )
        assign_facility(
            facility=facility,
            user=operations_manager,
            role_type=FacilityAssignment.RoleType.OPERATIONS_MANAGER,
            created_by=super_admin_user,
        )
        api_client.force_authenticate(user=officer)

        created = api_client.post(
            reverse("api_v1:security-incident-list"),
            {
                "facility": str(facility.id),
                "incident_type": "Manual emergency",
                "description": "Emergency reported by staff",
                "location": "Lobby",
                "severity_level": Incident.Severity.CRITICAL,
                "assigned_to": str(officer.id),
            },
            format="json",
        )
        assert created.status_code == status.HTTP_201_CREATED
        incident_id = created.data["id"]

        started = api_client.post(
            reverse(
                "api_v1:security-incident-start-investigation",
                kwargs={"pk": incident_id},
            ),
            {"assigned_to": str(officer.id)},
            format="json",
        )
        assert started.status_code == status.HTTP_200_OK
        assert started.data["status"] == Incident.Status.INVESTIGATION

        note_response = api_client.post(
            reverse(
                "api_v1:security-incident-notes",
                kwargs={"pk": incident_id},
            ),
            {"body": "Initial investigation note"},
            format="json",
        )
        assert note_response.status_code == status.HTTP_201_CREATED
        assert note_response.data["body"] == "Initial investigation note"

        action_response = api_client.post(
            reverse(
                "api_v1:security-incident-actions",
                kwargs={"pk": incident_id},
            ),
            {"action_taken": "Evacuated lobby", "notes": "No injuries"},
            format="json",
        )
        assert action_response.status_code == status.HTTP_201_CREATED
        assert action_response.data["completed_at"] is None
        assert action_response.data["completed_by_id"] is None

        action_completion_url = reverse(
            "api_v1:security-incident-action-completion",
            kwargs={"pk": incident_id, "action_id": action_response.data["id"]},
        )
        blocked_close = api_client.post(
            reverse("api_v1:security-incident-close", kwargs={"pk": incident_id}),
            {"final_report": "Incident cannot close with pending actions."},
            format="json",
        )
        assert blocked_close.status_code == status.HTTP_409_CONFLICT
        assert api_client.patch(
            action_completion_url,
            {"completed": True},
            format="json",
        ).status_code == status.HTTP_200_OK

        transferred = api_client.post(
            reverse(
                "api_v1:security-incident-transfer",
                kwargs={"pk": incident_id},
            ),
            {"assigned_to": str(operations_manager.id)},
            format="json",
        )
        assert transferred.status_code == status.HTTP_200_OK
        assert transferred.data["status"] == Incident.Status.TRANSFERRED

        closed = api_client.post(
            reverse(
                "api_v1:security-incident-close",
                kwargs={"pk": incident_id},
            ),
            {"final_report": "Incident resolved safely."},
            format="json",
        )
        assert closed.status_code == status.HTTP_200_OK
        assert closed.data["status"] == Incident.Status.CLOSED

        history = api_client.get(
            reverse(
                "api_v1:security-incident-actions",
                kwargs={"pk": incident_id},
            )
        )
        assert history.status_code == status.HTTP_200_OK
        assert history.data["count"] == 1
        assert api_client.put(
            reverse(
                "api_v1:security-incident-actions",
                kwargs={"pk": incident_id},
            ),
            {},
            format="json",
        ).status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_operations_and_suspended_users_cannot_mutate_security(
        self,
        api_client,
        role_operations_manager,
        role_security_officer,
        super_admin_user,
    ):
        facility = create_facility(created_by=super_admin_user, name="Denied")
        operations_manager = create_user(
            role=role_operations_manager,
            suffix="operations-denied",
        )
        suspended_officer = create_user(
            role=role_security_officer,
            suffix="security-suspended",
        )
        suspended_officer.status = User.STATUS_SUSPENDED
        suspended_officer.save(update_fields=["status"])
        alert = create_alert(facility=facility, created_by=super_admin_user)
        url = reverse("api_v1:security-alert-review", kwargs={"pk": alert.id})

        api_client.force_authenticate(user=operations_manager)
        assert api_client.post(url, {}).status_code == status.HTTP_403_FORBIDDEN
        api_client.force_authenticate(user=suspended_officer)
        assert api_client.post(url, {}).status_code == status.HTTP_403_FORBIDDEN

    def test_snapshot_and_evidence_downloads_never_expose_storage_urls(
        self,
        api_client,
        role_security_officer,
        super_admin_user,
        monkeypatch,
        tmp_path,
    ):
        officer = create_user(role=role_security_officer, suffix="security-files")
        facility = create_facility(created_by=super_admin_user, name="Evidence")
        assign_facility(
            facility=facility,
            user=officer,
            role_type=FacilityAssignment.RoleType.SECURITY_OFFICER,
            created_by=super_admin_user,
        )
        alert = create_alert(facility=facility, created_by=officer)
        alert.snapshot_image.name = "security/alerts/example.jpg"
        incident = create_manual_incident(
            facility_id=facility.id,
            actor=officer,
            incident_type="Evidence test",
            description="Evidence upload test",
            location="Lobby",
            severity_level=Incident.Severity.MEDIUM,
        )
        api_client.force_authenticate(user=officer)

        snapshot_stream = BytesIO(b"snapshot")
        snapshot_stream.name = "security/alerts/example.jpg"
        with patch(
            "api.v1.security_officer.views.open_authorized_protected_file",
            return_value=snapshot_stream,
        ):
            snapshot = api_client.get(
                reverse(
                    "api_v1:security-alert-snapshot",
                    kwargs={"pk": alert.id},
                )
            )
        assert snapshot.status_code == status.HTTP_200_OK
        assert "attachment" in snapshot["Content-Disposition"]

        file_field = Attachment._meta.get_field("file")
        monkeypatch.setattr(file_field, "storage", FileSystemStorage(location=tmp_path))
        uploaded = api_client.post(
            reverse(
                "api_v1:security-incident-evidence",
                kwargs={"pk": incident.id},
            ),
            {"file": SimpleUploadedFile("evidence.txt", b"secured evidence")},
            format="multipart",
        )
        assert uploaded.status_code == status.HTTP_201_CREATED
        assert "file" not in uploaded.data
        assert uploaded.data["download_url"].endswith(
            f"/security/evidence/{uploaded.data['id']}/download/"
        )

        evidence_stream = BytesIO(b"secured evidence")
        with patch(
            "api.v1.security_officer.views.open_authorized_attachment",
            return_value=evidence_stream,
        ):
            downloaded = api_client.get(uploaded.data["download_url"])
        assert downloaded.status_code == status.HTTP_200_OK
        assert "evidence.txt" in downloaded["Content-Disposition"]
