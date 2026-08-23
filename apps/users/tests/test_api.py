import uuid

import pytest
from django.urls import reverse
from rest_framework import status

from apps.users.models import Role, User


@pytest.mark.django_db
class TestRoleEndpoint:
    def test_list_roles_requires_authentication(self, api_client):
        url = reverse("role-list")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_authenticated_user_can_list_roles(
        self, authenticated_client, role_super_admin, role_construction_manager
    ):
        url = reverse("role-list")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 4


@pytest.mark.django_db
class TestUserEndpoint:
    @pytest.mark.parametrize(
        "role_name",
        [
            "super_admin",
            "construction_manager",
            "operations_manager",
            "security_officer",
        ],
    )
    def test_super_admin_can_create_each_existing_role(
        self,
        authenticated_client,
        role_name,
    ):
        url = reverse("user-list")
        role = Role.objects.get(name=role_name)
        payload = {
            "full_name": f"New {role.get_name_display()}",
            "email": f"new-{role_name}@sflms.test",
            "phone": "0100000000",
            "username": f"new_{role_name}",
            "role": str(role.id),
            "status": "active",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        }
        response = authenticated_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        created = User.objects.get(email=payload["email"])
        assert created.role.name == role_name
        assert created.check_password(payload["password"])
        assert response.data["role_name"] == role_name

    def test_create_user_returns_canonical_response_schema(
        self,
        authenticated_client,
        role_construction_manager,
    ):
        payload = self._payload(role_construction_manager)
        response = authenticated_client.post(
            reverse("user-list"), payload, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert set(response.data) == {
            "id",
            "full_name",
            "email",
            "phone",
            "username",
            "role",
            "role_name",
            "profile_image",
            "status",
            "last_login",
            "created_at",
            "updated_at",
        }
        assert str(response.data["role"]) == str(role_construction_manager.id)
        assert response.data["role_name"] == role_construction_manager.name
        assert response.data["last_login"] is None
        assert response.data["created_at"]
        assert response.data["updated_at"]
        assert "password" not in response.data
        assert "confirm_password" not in response.data

    def test_create_user_without_role_is_rejected(
        self,
        authenticated_client,
        role_construction_manager,
    ):
        payload = self._payload(role_construction_manager)
        payload.pop("role")

        response = authenticated_client.post(
            reverse("user-list"), payload, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "role" in response.data["error"]["details"]
        assert not User.objects.filter(email=payload["email"]).exists()

    def test_duplicate_username_is_rejected(
        self,
        authenticated_client,
        role_construction_manager,
    ):
        User.objects.create_user(
            email="existing-username@sflms.test",
            username="duplicate_user",
            full_name="Existing User",
            password="StrongPass123!",
            role=role_construction_manager,
        )
        payload = self._payload(role_construction_manager)
        payload["username"] = "duplicate_user"

        response = authenticated_client.post(
            reverse("user-list"), payload, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "username" in response.data["error"]["details"]

    def test_duplicate_email_is_rejected(
        self,
        authenticated_client,
        role_construction_manager,
    ):
        User.objects.create_user(
            email="duplicate-email@sflms.test",
            username="existing_email_user",
            full_name="Existing User",
            password="StrongPass123!",
            role=role_construction_manager,
        )
        payload = self._payload(role_construction_manager)
        payload["email"] = "duplicate-email@sflms.test"

        response = authenticated_client.post(
            reverse("user-list"), payload, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data["error"]["details"]

    def test_invalid_role_is_rejected(
        self,
        authenticated_client,
        role_construction_manager,
    ):
        payload = self._payload(role_construction_manager)
        payload["role"] = str(uuid.uuid4())

        response = authenticated_client.post(
            reverse("user-list"), payload, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "role" in response.data["error"]["details"]

    def test_super_admin_can_reassign_role_and_receives_canonical_response(
        self,
        authenticated_client,
        construction_manager_user,
        role_operations_manager,
    ):
        response = authenticated_client.patch(
            reverse("user-detail", args=[construction_manager_user.pk]),
            {
                "full_name": "Updated Manager",
                "phone": "0500000000",
                "role": str(role_operations_manager.pk),
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        construction_manager_user.refresh_from_db()
        assert construction_manager_user.role == role_operations_manager
        assert construction_manager_user.full_name == "Updated Manager"
        assert response.data["id"] == str(construction_manager_user.pk)
        assert response.data["role_name"] == Role.OPERATIONS_MANAGER
        assert response.data["last_login"] is None
        assert response.data["created_at"]
        assert response.data["updated_at"]

    def test_invalid_role_reassignment_is_rejected(
        self,
        authenticated_client,
        construction_manager_user,
    ):
        response = authenticated_client.patch(
            reverse("user-detail", args=[construction_manager_user.pk]),
            {"role": str(uuid.uuid4())},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "role" in response.data["error"]["details"]
        construction_manager_user.refresh_from_db()
        assert construction_manager_user.role.name == Role.CONSTRUCTION_MANAGER

    def test_delete_soft_deactivates_account_and_preserves_record(
        self,
        authenticated_client,
        construction_manager_user,
    ):
        response = authenticated_client.delete(
            reverse("user-detail", args=[construction_manager_user.pk])
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        construction_manager_user.refresh_from_db()
        assert construction_manager_user.status == User.STATUS_INACTIVE
        assert not construction_manager_user.is_active
        assert User.objects.filter(pk=construction_manager_user.pk).exists()

    def test_super_admin_can_reactivate_an_inactive_account(
        self,
        authenticated_client,
        construction_manager_user,
    ):
        construction_manager_user.status = User.STATUS_INACTIVE
        construction_manager_user.save(update_fields=["status", "updated_at"])

        response = authenticated_client.patch(
            reverse("user-detail", args=[construction_manager_user.pk]),
            {"status": User.STATUS_ACTIVE},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        construction_manager_user.refresh_from_db()
        assert construction_manager_user.status == User.STATUS_ACTIVE
        assert construction_manager_user.is_active
        assert response.data["status"] == User.STATUS_ACTIVE
        assert response.data["role_name"] == Role.CONSTRUCTION_MANAGER

    def test_updating_another_user_does_not_modify_super_admin_account(
        self,
        authenticated_client,
        super_admin_user,
        construction_manager_user,
        role_security_officer,
    ):
        admin_snapshot = {
            "email": super_admin_user.email,
            "username": super_admin_user.username,
            "role_id": super_admin_user.role_id,
            "status": super_admin_user.status,
            "password": super_admin_user.password,
        }

        response = authenticated_client.patch(
            reverse("user-detail", args=[construction_manager_user.pk]),
            {"role": str(role_security_officer.pk)},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        super_admin_user.refresh_from_db()
        assert {
            "email": super_admin_user.email,
            "username": super_admin_user.username,
            "role_id": super_admin_user.role_id,
            "status": super_admin_user.status,
            "password": super_admin_user.password,
        } == admin_snapshot

    def test_super_admin_can_filter_users_by_status(
        self,
        authenticated_client,
        construction_manager_user,
        suspended_user,
    ):
        response = authenticated_client.get(
            reverse("user-list"), {"status": User.STATUS_SUSPENDED}
        )

        assert response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in response.data["results"]] == [
            str(suspended_user.pk)
        ]

    def test_super_admin_can_order_paginated_users_server_side(
        self,
        authenticated_client,
        role_construction_manager,
    ):
        User.objects.create_user(
            email="zulu@sflms.test",
            username="zulu",
            full_name="Zulu User",
            password="StrongPass123!",
            role=role_construction_manager,
        )
        User.objects.create_user(
            email="alpha@sflms.test",
            username="alpha",
            full_name="Alpha User",
            password="StrongPass123!",
            role=role_construction_manager,
        )

        response = authenticated_client.get(
            reverse("user-list"), {"ordering": "full_name"}
        )

        assert response.status_code == status.HTTP_200_OK
        names = [item["full_name"] for item in response.data["results"]]
        assert names == sorted(names)

    @pytest.mark.parametrize(
        ("password", "expected_fragment"),
        [
            ("password", "common"),
            ("12345678", "numeric"),
            ("Short1!", "short"),
        ],
    )
    def test_weak_passwords_are_rejected(
        self,
        authenticated_client,
        role_construction_manager,
        password,
        expected_fragment,
    ):
        payload = self._payload(role_construction_manager)
        payload["password"] = password
        payload["confirm_password"] = password

        response = authenticated_client.post(
            reverse("user-list"), payload, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        messages = " ".join(response.data["error"]["details"]["password"])
        assert expected_fragment in messages.lower()

    @staticmethod
    def _payload(role):
        return {
            "full_name": "New Manager",
            "email": "newmanager@sflms.test",
            "phone": "0100000000",
            "username": "newmanager",
            "role": str(role.id),
            "status": "active",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        }

    def test_create_user_password_mismatch_rejected(self, authenticated_client, role_construction_manager):
        url = reverse("user-list")
        payload = {
            "full_name": "Bad User",
            "email": "bad@sflms.test",
            "username": "baduser",
            "role": str(role_construction_manager.id),
            "password": "StrongPass123!",
            "confirm_password": "Mismatch123!",
        }
        response = authenticated_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_super_admin_user_list_is_object_scoped(self, api_client, construction_manager_user):
        api_client.force_authenticate(user=construction_manager_user)
        url = reverse("user-list")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in response.data["results"]] == [
            str(construction_manager_user.pk)
        ]

    def test_me_endpoint_returns_current_user(self, api_client, construction_manager_user):
        api_client.force_authenticate(user=construction_manager_user)
        url = reverse("user-me")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == construction_manager_user.email

    def test_me_endpoint_cannot_change_role_or_status(
        self,
        api_client,
        construction_manager_user,
        role_super_admin,
    ):
        api_client.force_authenticate(user=construction_manager_user)
        url = reverse("user-me")
        response = api_client.patch(
            url,
            {"role": str(role_super_admin.id), "status": User.STATUS_SUSPENDED},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        construction_manager_user.refresh_from_db()
        assert construction_manager_user.role.name == "construction_manager"
        assert construction_manager_user.status == User.STATUS_ACTIVE

    def test_change_password_flow(self, api_client, construction_manager_user):
        api_client.force_authenticate(user=construction_manager_user)
        url = reverse("user-change-password")
        response = api_client.post(
            url,
            {"old_password": "StrongPass123!", "new_password": "NewerPass456!"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        construction_manager_user.refresh_from_db()
        assert construction_manager_user.check_password("NewerPass456!")

    def test_change_password_wrong_old_password_rejected(self, api_client, construction_manager_user):
        api_client.force_authenticate(user=construction_manager_user)
        url = reverse("user-change-password")
        response = api_client.post(
            url,
            {"old_password": "WrongPass!", "new_password": "NewerPass456!"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_change_password_applies_configured_password_validators(
        self, api_client, construction_manager_user
    ):
        api_client.force_authenticate(user=construction_manager_user)
        url = reverse("user-change-password")
        response = api_client.post(
            url,
            {"old_password": "StrongPass123!", "new_password": "12345678"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["success"] is False
        assert response.data["error"]["code"] == status.HTTP_400_BAD_REQUEST
        construction_manager_user.refresh_from_db()
        assert construction_manager_user.check_password("StrongPass123!")
