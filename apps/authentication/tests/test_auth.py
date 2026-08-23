from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.test import override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework_simplejwt.tokens import AccessToken

from apps.users.models import User


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

    def test_active_roleless_account_is_rejected(self, api_client):
        User.objects.create_user(
            email="roleless@sflms.test",
            username="roleless",
            full_name="Roleless User",
            password="StrongPass123!",
            role=None,
        )

        response = api_client.post(
            reverse("auth-login"),
            {"email": "roleless@sflms.test", "password": "StrongPass123!"},
            format="json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "no assigned role" in response.data["error"]["message"]


@pytest.mark.django_db
class TestRefresh:
    def test_expired_access_token_is_rejected(self, api_client, super_admin_user):
        token = AccessToken.for_user(super_admin_user)
        token.set_exp(lifetime=timedelta(seconds=-1))
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = api_client.get(reverse("user-me"))

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

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
        assert "refresh" in response.data
        reused = api_client.post(refresh_url, {"refresh": refresh_token}, format="json")
        assert reused.status_code == status.HTTP_401_UNAUTHORIZED

    def test_refresh_with_invalid_token_fails(self, api_client):
        refresh_url = reverse("auth-refresh")
        response = api_client.post(refresh_url, {"refresh": "not-a-real-token"}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_refresh_rejects_an_account_suspended_after_login(
        self, api_client, super_admin_user
    ):
        login = api_client.post(
            reverse("auth-login"),
            {"email": "admin@sflms.test", "password": "StrongPass123!"},
            format="json",
        )
        super_admin_user.status = User.STATUS_SUSPENDED
        super_admin_user.save(update_fields=["status", "updated_at"])

        response = api_client.post(
            reverse("auth-refresh"),
            {"refresh": login.data["refresh"]},
            format="json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestLogout:
    def test_logout_blacklists_refresh_token_without_access_token(
        self, api_client, super_admin_user
    ):
        login_url = reverse("auth-login")
        login_response = api_client.post(
            login_url, {"email": "admin@sflms.test", "password": "StrongPass123!"}, format="json"
        )
        refresh_token = login_response.data["refresh"]
        logout_url = reverse("auth-logout")
        response = api_client.post(logout_url, {"refresh": refresh_token}, format="json")
        assert response.status_code == status.HTTP_205_RESET_CONTENT

        # The blacklisted refresh token must no longer be usable.
        refresh_url = reverse("auth-refresh")
        second_response = api_client.post(refresh_url, {"refresh": refresh_token}, format="json")
        assert second_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_rejects_an_invalid_refresh_token(self, api_client):
        logout_url = reverse("auth-logout")
        response = api_client.post(logout_url, {"refresh": "whatever"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestPasswordReset:
    def test_invalid_token_is_checked_before_password_policy(
        self, api_client, construction_manager_user
    ):
        uid = urlsafe_base64_encode(force_bytes(construction_manager_user.pk))

        response = api_client.post(
            reverse("auth-password-reset-confirm"),
            {
                "uid": uid,
                "token": "invalid-token",
                "new_password": "12345678",
                "confirm_password": "12345678",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        details = response.data["error"]["details"]
        assert "token" in details
        assert "new_password" not in details

    @override_settings(PASSWORD_RESET_TIMEOUT=1800)
    def test_expired_reset_token_is_rejected(self, api_client, construction_manager_user):
        uid = urlsafe_base64_encode(force_bytes(construction_manager_user.pk))
        issued_at = datetime(2026, 1, 1, 12, 0, 0)
        with patch.object(default_token_generator, "_now", return_value=issued_at):
            token = default_token_generator.make_token(construction_manager_user)
        with patch.object(
            default_token_generator,
            "_now",
            return_value=issued_at + timedelta(seconds=1801),
        ):
            response = api_client.post(
                reverse("auth-password-reset-confirm"),
                {
                    "uid": uid,
                    "token": token,
                    "new_password": "ChangedPass456!",
                    "confirm_password": "ChangedPass456!",
                },
                format="json",
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "invalid or expired" in str(response.data["error"]["details"]["token"])

    def test_password_reset_revokes_existing_access_and_refresh_tokens(
        self, api_client, construction_manager_user
    ):
        login = api_client.post(
            reverse("auth-login"),
            {
                "email": construction_manager_user.email,
                "password": "StrongPass123!",
            },
            format="json",
        )
        construction_manager_user.refresh_from_db()
        uid = urlsafe_base64_encode(force_bytes(construction_manager_user.pk))
        token = default_token_generator.make_token(construction_manager_user)

        reset = api_client.post(
            reverse("auth-password-reset-confirm"),
            {
                "uid": uid,
                "token": token,
                "new_password": "ChangedPass456!",
                "confirm_password": "ChangedPass456!",
            },
            format="json",
        )

        assert reset.status_code == status.HTTP_200_OK
        old_refresh = api_client.post(
            reverse("auth-refresh"),
            {"refresh": login.data["refresh"]},
            format="json",
        )
        assert old_refresh.status_code == status.HTTP_401_UNAUTHORIZED
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        assert api_client.get(reverse("user-me")).status_code == status.HTTP_401_UNAUTHORIZED
