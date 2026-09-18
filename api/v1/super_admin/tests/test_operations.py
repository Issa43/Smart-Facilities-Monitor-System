from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import serializers, status

from api.v1.super_admin.serializers import ProjectWriteSerializer
from apps.projects.models import Project, ProjectAssignment
from apps.users.models import User


def project_payload(manager):
    return {
        "name": "Atomic Assignment Project",
        "facility_type": Project.FacilityType.COMMERCIAL,
        "description": "Project created with its primary manager atomically.",
        "location": "Riyadh",
        "start_date": date.today().isoformat(),
        "expected_completion_date": (date.today() + timedelta(days=90)).isoformat(),
        "primary_manager_id": str(manager.pk),
    }


@pytest.mark.django_db
class TestSuperAdminProjectOperations:
    def test_project_and_primary_manager_are_created_atomically(
        self,
        authenticated_client,
        construction_manager_user,
        super_admin_user,
    ):
        response = authenticated_client.post(
            reverse("api_v1:project-list"),
            project_payload(construction_manager_user),
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED, response.data
        project = Project.objects.get(pk=response.data["id"])
        assignment = ProjectAssignment.objects.get(
            project=project,
            role_type=ProjectAssignment.RoleType.PRIMARY_MANAGER,
            is_active=True,
        )
        assert assignment.user == construction_manager_user
        assert assignment.created_by == super_admin_user
        assert str(response.data["primary_manager_id"]) == str(construction_manager_user.pk)

    def test_project_creation_rolls_back_when_manager_assignment_fails(
        self,
        authenticated_client,
        construction_manager_user,
    ):
        with patch.object(
            ProjectWriteSerializer,
            "_set_primary_manager",
            side_effect=serializers.ValidationError(
                {"primary_manager_id": ["Assignment failed."]}
            ),
        ):
            response = authenticated_client.post(
                reverse("api_v1:project-list"),
                project_payload(construction_manager_user),
                format="json",
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Project.objects.filter(name="Atomic Assignment Project").exists()

    def test_project_update_replaces_primary_manager_in_one_transaction(
        self,
        authenticated_client,
        construction_manager_user,
        role_construction_manager,
    ):
        created = authenticated_client.post(
            reverse("api_v1:project-list"),
            project_payload(construction_manager_user),
            format="json",
        )
        replacement = User.objects.create_user(
            email="replacement-manager@sflms.test",
            username="replacement_manager",
            full_name="Replacement Manager",
            password="StrongPass123!",
            role=role_construction_manager,
        )

        response = authenticated_client.patch(
            reverse("api_v1:project-detail", kwargs={"pk": created.data["id"]}),
            {"primary_manager_id": str(replacement.pk)},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK, response.data
        assignments = ProjectAssignment.all_objects.filter(
            project_id=created.data["id"],
            role_type=ProjectAssignment.RoleType.PRIMARY_MANAGER,
        )
        assert assignments.filter(user=replacement, is_active=True).count() == 1
        assert assignments.filter(user=construction_manager_user, is_active=True).count() == 0
        assert str(response.data["primary_manager_id"]) == str(replacement.pk)


@pytest.mark.django_db
def test_super_admin_can_open_every_batch4_operational_collection(authenticated_client):
    route_names = [
        "operations-facility-list",
        "operations-asset-list",
        "operations-maintenance-order-list",
        "operations-fault-list",
        "security-alert-list",
        "security-incident-list",
        "security-camera-list",
        "security-document-list",
        "report-request-list",
        "notification-list",
    ]

    responses = {
        route_name: authenticated_client.get(reverse(f"api_v1:{route_name}"))
        for route_name in route_names
    }

    assert {
        route_name: response.status_code for route_name, response in responses.items()
    } == {route_name: status.HTTP_200_OK for route_name in route_names}
