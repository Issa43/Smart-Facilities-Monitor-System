from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import pytest
from django.core import mail
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

    def test_login_ignores_the_letter_case_of_the_email(
        self, api_client, role_operations_manager
    ):
        """An address stored with capitals still logs in when typed in lower case.

        Both password-reset paths resolve accounts with `iexact`, so an account
        whose stored address has any uppercase letter could reset its password
        from the lower-case form and then be refused at login with the password
        it had just set. Login now resolves the identifier the same way.
        """

        User.objects.create_user(
            email="Mixed.Case@sflms.test",
            username="mixedcase",
            full_name="Mixed Case",
            password="StrongPass123!",
            role=role_operations_manager,
            status=User.STATUS_ACTIVE,
        )
        url = reverse("auth-login")

        for typed in ("Mixed.Case@sflms.test", "mixed.case@sflms.test", "MIXED.CASE@SFLMS.TEST"):
            response = api_client.post(
                url, {"email": typed, "password": "StrongPass123!"}, format="json"
            )
            assert response.status_code == status.HTTP_200_OK, typed

    def test_case_insensitive_login_still_requires_the_right_password(
        self, api_client, role_operations_manager
    ):
        """Relaxing the lookup must not relax the credential check."""

        User.objects.create_user(
            email="Mixed.Case2@sflms.test",
            username="mixedcase2",
            full_name="Mixed Case Two",
            password="StrongPass123!",
            role=role_operations_manager,
            status=User.STATUS_ACTIVE,
        )
        response = api_client.post(
            reverse("auth-login"),
            {"email": "mixed.case2@sflms.test", "password": "WrongPassword!"},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_addresses_differing_only_by_case_are_never_guessed_between(
        self, api_client, role_operations_manager
    ):
        """`email` is unique case-sensitively, so such a pair can exist.

        Picking either one would let a password authenticate against an account
        its owner did not name, so the ambiguous form is refused outright while
        each exact spelling keeps working.
        """

        for index, address in enumerate(("Twin@sflms.test", "twin@sflms.test")):
            User.objects.create_user(
                email=address,
                username=f"twin{index}",
                full_name="Twin",
                password=f"StrongPass{index}123!",
                role=role_operations_manager,
                status=User.STATUS_ACTIVE,
            )
        url = reverse("auth-login")

        ambiguous = api_client.post(
            url, {"email": "TWIN@sflms.test", "password": "StrongPass0123!"}, format="json"
        )
        assert ambiguous.status_code == status.HTTP_401_UNAUTHORIZED

        for index, address in enumerate(("Twin@sflms.test", "twin@sflms.test")):
            exact = api_client.post(
                url, {"email": address, "password": f"StrongPass{index}123!"}, format="json"
            )
            assert exact.status_code == status.HTTP_200_OK, address

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

    def test_access_token_rejects_an_account_suspended_after_login(
        self, api_client, super_admin_user
    ):
        login = api_client.post(
            reverse("auth-login"),
            {"email": "admin@sflms.test", "password": "StrongPass123!"},
            format="json",
        )
        super_admin_user.status = User.STATUS_SUSPENDED
        super_admin_user.save(update_fields=["status", "updated_at"])
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        response = api_client.get(reverse("user-me"))

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


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

    def test_password_reset_token_cannot_be_reused(
        self, api_client, construction_manager_user
    ):
        uid = urlsafe_base64_encode(force_bytes(construction_manager_user.pk))
        token = default_token_generator.make_token(construction_manager_user)
        payload = {
            "uid": uid,
            "token": token,
            "new_password": "ChangedPass456!",
            "confirm_password": "ChangedPass456!",
        }

        first = api_client.post(
            reverse("auth-password-reset-confirm"), payload, format="json"
        )
        second = api_client.post(
            reverse("auth-password-reset-confirm"), payload, format="json"
        )

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_400_BAD_REQUEST
        assert "invalid or expired" in str(
            second.data["error"]["details"]["token"]
        )


@pytest.mark.django_db
class TestDevPasswordResetLink:
    """The local-development shortcut that returns a reset link directly.

    It returns the link in the response body so a developer never has to go
    looking for it in an inbox, which also means it must send no mail at all. It
    must be impossible to use outside local development, and must never become a
    second way to change a password.
    """

    url = "/api/v1/auth/dev/password-reset-link/"

    @override_settings(DEBUG=True)
    def test_debug_mode_returns_a_usable_reset_link(self, api_client, super_admin_user):
        response = api_client.post(self.url, {"email": super_admin_user.email}, format="json")

        assert response.status_code == status.HTTP_200_OK
        reset_url = response.data["reset_url"]
        assert "/reset-password?" in reset_url
        assert "uid=" in reset_url and "token=" in reset_url

    @override_settings(DEBUG=True)
    def test_the_link_carries_the_real_uid_and_a_valid_token(
        self, api_client, super_admin_user
    ):
        response = api_client.post(self.url, {"email": super_admin_user.email}, format="json")
        query = parse_qs(urlparse(response.data["reset_url"]).query)

        assert query["uid"][0] == urlsafe_base64_encode(force_bytes(super_admin_user.pk))
        assert default_token_generator.check_token(super_admin_user, query["token"][0])

    @override_settings(DEBUG=True)
    def test_the_generated_link_drives_the_normal_confirmation_endpoint(
        self, api_client, super_admin_user
    ):
        """The shortcut only produces a link; the real endpoint does the work."""

        generated = api_client.post(self.url, {"email": super_admin_user.email}, format="json")
        query = parse_qs(urlparse(generated.data["reset_url"]).query)

        confirm = api_client.post(
            reverse("auth-password-reset-confirm"),
            {
                "uid": query["uid"][0],
                "token": query["token"][0],
                "new_password": "DevShortcut456!",
                "confirm_password": "DevShortcut456!",
            },
            format="json",
        )

        assert confirm.status_code == status.HTTP_200_OK
        super_admin_user.refresh_from_db()
        assert super_admin_user.check_password("DevShortcut456!")

    @override_settings(DEBUG=True)
    def test_it_sends_no_mail_and_opens_no_smtp_connection(
        self, api_client, super_admin_user
    ):
        """The link is delivered in the response, never by email.

        Pointing EMAIL_BACKEND at the real SMTP backend and at a port nothing
        listens on means any attempt to send would raise instead of passing
        quietly, so this fails loudly if the shortcut ever grows a send_mail
        call. No local mail sink has to be running for the shortcut to work.
        """

        mail.outbox.clear()
        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
            EMAIL_HOST="127.0.0.1",
            EMAIL_PORT=1,
            EMAIL_TIMEOUT=1,
        ):
            response = api_client.post(
                self.url, {"email": super_admin_user.email}, format="json"
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["reset_url"]
        assert mail.outbox == []

    @override_settings(DEBUG=True)
    def test_the_shortcut_resets_a_password_the_account_can_then_log_in_with(
        self, api_client, role_operations_manager
    ):
        """The whole chain, end to end, on an account created by this test."""

        account = User.objects.create_user(
            email="dev.shortcut.subject@sflms.test",
            username="devshortcutsubject",
            full_name="Dev Shortcut Subject",
            password="InitialPass123!",
            role=role_operations_manager,
            status=User.STATUS_ACTIVE,
        )
        new_password = "RotatedByShortcut789!"

        generated = api_client.post(self.url, {"email": account.email}, format="json")
        assert generated.status_code == status.HTTP_200_OK
        query = parse_qs(urlparse(generated.data["reset_url"]).query)

        confirm = api_client.post(
            reverse("auth-password-reset-confirm"),
            {
                "uid": query["uid"][0],
                "token": query["token"][0],
                "new_password": new_password,
                "confirm_password": new_password,
            },
            format="json",
        )
        assert confirm.status_code == status.HTTP_200_OK

        login = api_client.post(
            reverse("auth-login"),
            {"email": account.email, "password": new_password},
            format="json",
        )
        assert login.status_code == status.HTTP_200_OK
        assert login.data["access"]

        # The superseded password must not still work.
        stale = api_client.post(
            reverse("auth-login"),
            {"email": account.email, "password": "InitialPass123!"},
            format="json",
        )
        assert stale.status_code == status.HTTP_401_UNAUTHORIZED

    @override_settings(DEBUG=True)
    def test_a_generated_link_cannot_be_replayed_after_it_is_used(
        self, api_client, super_admin_user
    ):
        """The token is derived from the password hash, so using it burns it."""

        generated = api_client.post(self.url, {"email": super_admin_user.email}, format="json")
        query = parse_qs(urlparse(generated.data["reset_url"]).query)
        payload = {
            "uid": query["uid"][0],
            "token": query["token"][0],
            "new_password": "FirstRotation123!",
            "confirm_password": "FirstRotation123!",
        }

        first = api_client.post(reverse("auth-password-reset-confirm"), payload, format="json")
        assert first.status_code == status.HTTP_200_OK

        replay = api_client.post(reverse("auth-password-reset-confirm"), payload, format="json")
        assert replay.status_code == status.HTTP_400_BAD_REQUEST

    @override_settings(DEBUG=True)
    def test_generating_a_link_never_changes_the_password(
        self, api_client, super_admin_user
    ):
        original = super_admin_user.password
        api_client.post(self.url, {"email": super_admin_user.email}, format="json")

        super_admin_user.refresh_from_db()
        assert super_admin_user.password == original
        assert super_admin_user.check_password("StrongPass123!")

    def test_it_is_unavailable_when_debug_is_off(self, api_client, super_admin_user):
        """Default settings have DEBUG off, exactly as production does."""

        from django.conf import settings as django_settings

        assert django_settings.DEBUG is False
        response = api_client.post(self.url, {"email": super_admin_user.email}, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "reset_url" not in str(response.data)

    @override_settings(DEBUG=False)
    def test_debug_false_is_enforced_by_the_server_not_the_client(
        self, api_client, super_admin_user
    ):
        response = api_client.post(self.url, {"email": super_admin_user.email}, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @override_settings(DEBUG=True)
    def test_an_unknown_account_reveals_nothing_about_it(self, api_client):
        response = api_client.post(self.url, {"email": "nobody@example.test"}, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        body = str(response.data)
        assert "reset_url" not in body
        assert "nobody@example.test" not in body

    @override_settings(DEBUG=True)
    def test_a_suspended_account_gets_no_link(self, api_client, construction_manager_user):
        construction_manager_user.status = User.STATUS_SUSPENDED
        construction_manager_user.save(update_fields=["status"])

        response = api_client.post(
            self.url, {"email": construction_manager_user.email}, format="json"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @override_settings(DEBUG=True)
    def test_an_invalid_email_is_rejected(self, api_client):
        response = api_client.post(self.url, {"email": "not-an-email"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @override_settings(DEBUG=True)
    def test_the_shortcut_is_absent_from_the_published_api_schema(self):
        from drf_spectacular.generators import SchemaGenerator

        schema = SchemaGenerator().get_schema(request=None, public=True)
        assert "/api/v1/auth/dev/password-reset-link/" not in schema["paths"]
        # The production reset endpoints are still documented.
        assert "/api/v1/auth/password-reset/" in schema["paths"]
