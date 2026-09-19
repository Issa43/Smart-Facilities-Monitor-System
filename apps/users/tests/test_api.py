from io import BytesIO
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework import status

from apps.users.models import Permission, Role, User


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

    def test_non_admin_cannot_list_roles(
        self, api_client, construction_manager_user
    ):
        api_client.force_authenticate(user=construction_manager_user)

        response = api_client.get(reverse("role-list"))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_super_admin_can_replace_permissions_for_a_non_admin_role(
        self,
        authenticated_client,
        role_construction_manager,
    ):
        response = authenticated_client.put(
            reverse(
                "role-set-permissions",
                args=[role_construction_manager.pk],
            ),
            {
                "permissions": [
                    "project.view",
                    "report.generate",
                    "project.view",
                ]
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert set(
            role_construction_manager.permissions.values_list(
                "permission_name", flat=True
            )
        ) == {"project.view", "report.generate"}
        assert {
            item["permission_name"] for item in response.data["permissions"]
        } == {"project.view", "report.generate"}

    def test_unknown_permission_is_rejected_without_changing_existing_grants(
        self,
        authenticated_client,
        role_construction_manager,
    ):
        before = set(
            role_construction_manager.permissions.values_list(
                "permission_name", flat=True
            )
        )

        response = authenticated_client.put(
            reverse(
                "role-set-permissions",
                args=[role_construction_manager.pk],
            ),
            {"permissions": ["project.view", "not.a.permission"]},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert (
            set(
                role_construction_manager.permissions.values_list(
                    "permission_name", flat=True
                )
            )
            == before
        )

    def test_super_admin_break_glass_permissions_cannot_be_changed(
        self,
        authenticated_client,
        role_super_admin,
    ):
        before = set(
            role_super_admin.permissions.values_list("permission_name", flat=True)
        )

        response = authenticated_client.put(
            reverse("role-set-permissions", args=[role_super_admin.pk]),
            {"permissions": []},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "permissions" in response.data["error"]["details"]
        assert (
            set(role_super_admin.permissions.values_list("permission_name", flat=True))
            == before
        )

    @pytest.mark.parametrize(
        "role_name",
        [
            Role.CONSTRUCTION_MANAGER,
            Role.OPERATIONS_MANAGER,
            Role.SECURITY_OFFICER,
        ],
    )
    def test_non_admin_roles_cannot_change_role_permissions(
        self,
        api_client,
        role_name,
        role_construction_manager,
    ):
        actor_role = Role.objects.get(name=role_name)
        actor = User.objects.create_user(
            email=f"{role_name}-permissions@sflms.test",
            username=f"{role_name}_permissions",
            full_name=actor_role.get_name_display(),
            password="StrongPass123!",
            role=actor_role,
        )
        api_client.force_authenticate(actor)

        response = api_client.put(
            reverse(
                "role-set-permissions",
                args=[role_construction_manager.pk],
            ),
            {"permissions": ["project.view"]},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_inactive_super_admin_cannot_change_role_permissions(
        self,
        api_client,
        role_super_admin,
        role_construction_manager,
    ):
        actor = User.objects.create_user(
            email="inactive-admin-permissions@sflms.test",
            username="inactive_admin_permissions",
            full_name="Inactive Admin",
            password="StrongPass123!",
            role=role_super_admin,
            status=User.STATUS_SUSPENDED,
        )
        api_client.force_authenticate(actor)

        response = api_client.put(
            reverse(
                "role-set-permissions",
                args=[role_construction_manager.pk],
            ),
            {"permissions": ["project.view"]},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


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

    @pytest.mark.parametrize(
        "role_name",
        [
            Role.CONSTRUCTION_MANAGER,
            Role.OPERATIONS_MANAGER,
            Role.SECURITY_OFFICER,
        ],
    )
    def test_non_admin_roles_cannot_mutate_users(
        self,
        api_client,
        role_name,
        construction_manager_user,
    ):
        actor_role = Role.objects.get(name=role_name)
        actor = User.objects.create_user(
            email=f"{role_name}-user-admin@sflms.test",
            username=f"{role_name}_user_admin",
            full_name=actor_role.get_name_display(),
            password="StrongPass123!",
            role=actor_role,
        )
        api_client.force_authenticate(actor)

        responses = [
            api_client.post(reverse("user-list"), {}, format="json"),
            api_client.patch(
                reverse("user-detail", args=[construction_manager_user.pk]),
                {"status": User.STATUS_SUSPENDED},
                format="json",
            ),
            api_client.delete(
                reverse("user-detail", args=[construction_manager_user.pk])
            ),
        ]

        assert [response.status_code for response in responses] == [403, 403, 403]
        construction_manager_user.refresh_from_db()
        assert construction_manager_user.status == User.STATUS_ACTIVE

    def test_inactive_super_admin_cannot_mutate_users(
        self,
        api_client,
        role_super_admin,
        construction_manager_user,
    ):
        actor = User.objects.create_user(
            email="inactive-admin-users@sflms.test",
            username="inactive_admin_users",
            full_name="Inactive Admin",
            password="StrongPass123!",
            role=role_super_admin,
            status=User.STATUS_SUSPENDED,
        )
        api_client.force_authenticate(actor)

        response = api_client.patch(
            reverse("user-detail", args=[construction_manager_user.pk]),
            {"status": User.STATUS_SUSPENDED},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_super_admin_cannot_demote_or_suspend_their_own_account(
        self,
        authenticated_client,
        super_admin_user,
        role_security_officer,
    ):
        response = authenticated_client.patch(
            reverse("user-detail", args=[super_admin_user.pk]),
            {
                "role": str(role_security_officer.pk),
                "status": User.STATUS_SUSPENDED,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert set(response.data["error"]["details"]) == {"role", "status"}
        super_admin_user.refresh_from_db()
        assert super_admin_user.role.name == Role.SUPER_ADMIN
        assert super_admin_user.status == User.STATUS_ACTIVE

    def test_super_admin_cannot_remove_their_own_role_with_null(
        self,
        authenticated_client,
        super_admin_user,
    ):
        response = authenticated_client.patch(
            reverse("user-detail", args=[super_admin_user.pk]),
            {"role": None},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "role" in response.data["error"]["details"]
        super_admin_user.refresh_from_db()
        assert super_admin_user.role.name == Role.SUPER_ADMIN

    def test_super_admin_cannot_archive_their_own_account(
        self,
        authenticated_client,
        super_admin_user,
    ):
        response = authenticated_client.delete(
            reverse("user-detail", args=[super_admin_user.pk])
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "user" in response.data["error"]["details"]
        super_admin_user.refresh_from_db()
        assert super_admin_user.status == User.STATUS_ACTIVE

    def test_super_admin_can_edit_their_own_non_privileged_profile_fields(
        self,
        authenticated_client,
        super_admin_user,
    ):
        response = authenticated_client.patch(
            reverse("user-detail", args=[super_admin_user.pk]),
            {"full_name": "Updated Super Admin", "phone": "0501111111"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        super_admin_user.refresh_from_db()
        assert super_admin_user.full_name == "Updated Super Admin"
        assert super_admin_user.phone == "0501111111"

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

    def test_role_reassignment_cannot_make_an_active_user_roleless(
        self,
        authenticated_client,
        construction_manager_user,
    ):
        response = authenticated_client.patch(
            reverse("user-detail", args=[construction_manager_user.pk]),
            {"role": None},
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

    def test_me_endpoint_uploads_profile_image(self, api_client, construction_manager_user):
        image_bytes = BytesIO()
        Image.new("RGB", (2, 2), color="white").save(image_bytes, format="PNG")
        api_client.force_authenticate(user=construction_manager_user)

        response = api_client.patch(
            reverse("user-me"),
            {
                "profile_image": SimpleUploadedFile(
                    "avatar.png",
                    image_bytes.getvalue(),
                    content_type="image/png",
                )
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_200_OK
        construction_manager_user.refresh_from_db()
        assert construction_manager_user.profile_image.name.endswith("avatar.png")
        construction_manager_user.profile_image.storage.delete(
            construction_manager_user.profile_image.name
        )

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


@pytest.mark.django_db
class TestMachinePrincipalsExcludedFromUserAdministration:
    """Regression: AI service principals broke every consumer of /users/.

    They are created with ``role=None`` (apps/security/machine_credentials.py),
    cannot authenticate with a password, and are denied by every RBAC check.
    Returning them from the human user-administration endpoint made clients
    that require a role fail for the whole page, and offered non-human accounts
    in assignee pickers.
    """

    def _machine_principal(self):
        return User.objects.create_user(
            email=f"ai-{uuid.uuid4().hex}@machine.sflms.invalid",
            username=f"ai-{uuid.uuid4().hex}",
            full_name="AI service: camera ingestion",
            password=None,
            role=None,
            status=User.STATUS_ACTIVE,
        )

    def test_list_excludes_role_less_service_principals(
        self, authenticated_client, super_admin_user
    ):
        principal = self._machine_principal()
        response = authenticated_client.get(reverse("user-list"))

        assert response.status_code == status.HTTP_200_OK
        returned = {row["id"] for row in response.data["results"]}
        assert str(principal.pk) not in returned
        assert str(super_admin_user.pk) in returned
        # Every returned row carries a role, so a client may rely on it.
        assert all(row["role_name"] for row in response.data["results"])

    def test_count_and_pagination_match_the_returned_rows(
        self, authenticated_client, super_admin_user
    ):
        self._machine_principal()
        self._machine_principal()
        response = authenticated_client.get(reverse("user-list"))

        assert response.status_code == status.HTTP_200_OK
        # A client paginating on `count` must not be told about rows it will
        # never receive.
        assert response.data["count"] == len(response.data["results"])
        assert response.data["count"] == User.objects.exclude(role__isnull=True).count()

    def test_detail_routes_are_unchanged(self, authenticated_client, super_admin_user):
        """Only the listing changed.

        The rule that a real machine principal cannot be promoted to a human
        role is enforced elsewhere (it keys off the AI credential, not off a
        missing role) and is covered by
        apps/security/tests/test_machine_credentials.py.
        """

        principal = self._machine_principal()
        detail = reverse("user-detail", args=[principal.pk])
        assert authenticated_client.get(detail).status_code == status.HTTP_200_OK

    def test_the_principal_row_itself_is_preserved(self, authenticated_client, super_admin_user):
        """Exclusion is a visibility rule, never a deletion."""

        principal = self._machine_principal()
        authenticated_client.get(reverse("user-list"))
        assert User.objects.filter(pk=principal.pk).exists()
