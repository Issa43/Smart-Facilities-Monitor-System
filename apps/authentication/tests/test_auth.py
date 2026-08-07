import pytest
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
class TestLogin:
    def test_login_with_valid_credentials_returns_tokens(self, api_client, super_admin_user):
        url = reverse("auth-login")
        response = api_client.post(
            url, {"email": "admin@sflms.test", "password": "StrongPass123!"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data
        assert response.data["user"]["role"] == "super_admin"

    def test_login_with_wrong_password_fails(self, api_client, super_admin_user):
        url = reverse("auth-login")
        response = api_client.post(
            url, {"email": "admin@sflms.test", "password": "WrongPassword!"}, format="json"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_with_suspended_account_is_rejected(self, api_client, suspended_user):
        url = reverse("auth-login")
        response = api_client.post(
            url, {"email": "suspended@sflms.test", "password": "StrongPass123!"}, format="json"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_access_token_contains_role_claim(self, api_client, super_admin_user):
        import jwt

        url = reverse("auth-login")
        response = api_client.post(
            url, {"email": "admin@sflms.test", "password": "StrongPass123!"}, format="json"
        )
        decoded = jwt.decode(response.data["access"], options={"verify_signature": False})
        assert decoded["role"] == "super_admin"
        assert decoded["full_name"] == "Super Admin"


@pytest.mark.django_db
class TestRefresh:
    def test_refresh_returns_new_access_token(self, api_client, super_admin_user):
        login_url = reverse("auth-login")
        login_response = api_client.post(
            login_url, {"email": "admin@sflms.test", "password": "StrongPass123!"}, format="json"
        )
        refresh_token = login_response.data["refresh"]

        refresh_url = reverse("auth-refresh")
        response = api_client.post(refresh_url, {"refresh": refresh_token}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data

    def test_refresh_with_invalid_token_fails(self, api_client):
        refresh_url = reverse("auth-refresh")
        response = api_client.post(refresh_url, {"refresh": "not-a-real-token"}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestLogout:
    def test_logout_blacklists_refresh_token(self, api_client, super_admin_user):
        login_url = reverse("auth-login")
        login_response = api_client.post(
            login_url, {"email": "admin@sflms.test", "password": "StrongPass123!"}, format="json"
        )
        refresh_token = login_response.data["refresh"]
        access_token = login_response.data["access"]

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        logout_url = reverse("auth-logout")
        response = api_client.post(logout_url, {"refresh": refresh_token}, format="json")
        assert response.status_code == status.HTTP_205_RESET_CONTENT

        # The blacklisted refresh token must no longer be usable.
        refresh_url = reverse("auth-refresh")
        second_response = api_client.post(refresh_url, {"refresh": refresh_token}, format="json")
        assert second_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_requires_authentication(self, api_client):
        logout_url = reverse("auth-logout")
        response = api_client.post(logout_url, {"refresh": "whatever"}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
