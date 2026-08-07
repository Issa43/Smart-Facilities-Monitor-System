import pytest
from django.urls import reverse
from rest_framework import status

from apps.users.models import User


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
    def test_super_admin_can_create_user(self, authenticated_client, role_construction_manager):
        url = reverse("user-list")
        payload = {
            "full_name": "New Manager",
            "email": "newmanager@sflms.test",
            "phone": "0100000000",
            "username": "newmanager",
            "role": str(role_construction_manager.id),
            "status": "active",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        }
        response = authenticated_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert User.objects.filter(email="newmanager@sflms.test").exists()

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

    def test_non_super_admin_cannot_list_users(self, api_client, construction_manager_user):
        api_client.force_authenticate(user=construction_manager_user)
        url = reverse("user-list")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

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
