import pytest
from django.db import IntegrityError

from apps.users.models import Permission, Role, User


@pytest.mark.django_db
class TestRoleModel:
    def test_seeded_role(self):
        role = Role.objects.get(name=Role.SUPER_ADMIN)
        assert role.name == "super_admin"
        assert str(role) == "Super Admin"

    def test_role_name_is_unique(self):
        with pytest.raises(IntegrityError):
            Role.objects.create(name=Role.SUPER_ADMIN)


@pytest.mark.django_db
class TestPermissionModel:
    def test_create_permission(self, role_super_admin):
        perm = Permission.objects.create(role=role_super_admin, permission_name="test.project.create")
        assert str(perm) == "super_admin:test.project.create"

    def test_unique_permission_per_role(self, role_super_admin):
        Permission.objects.create(role=role_super_admin, permission_name="test.project.create")
        with pytest.raises(IntegrityError):
            Permission.objects.create(role=role_super_admin, permission_name="test.project.create")


@pytest.mark.django_db
class TestUserModel:
    def test_create_user_hashes_password(self, role_construction_manager):
        user = User.objects.create_user(
            email="test@sflms.test",
            username="testuser",
            full_name="Test User",
            password="StrongPass123!",
            role=role_construction_manager,
        )
        assert user.password != "StrongPass123!"
        assert user.check_password("StrongPass123!")

    def test_email_is_username_field(self):
        assert User.USERNAME_FIELD == "email"

    def test_is_active_reflects_status(self, role_construction_manager):
        user = User.objects.create_user(
            email="active@sflms.test",
            username="activeuser",
            full_name="Active User",
            password="StrongPass123!",
            role=role_construction_manager,
            status=User.STATUS_ACTIVE,
        )
        assert user.is_active is True

        user.status = User.STATUS_SUSPENDED
        assert user.is_active is False

    def test_create_superuser(self):
        admin = User.objects.create_superuser(
            email="root@sflms.test",
            username="root",
            full_name="Root",
            password="StrongPass123!",
        )
        assert admin.is_staff is True
        assert admin.is_superuser is True
        assert admin.role is not None
        assert admin.role.name == Role.SUPER_ADMIN

    def test_email_uniqueness_enforced(self, role_construction_manager):
        User.objects.create_user(
            email="dup@sflms.test",
            username="dupuser1",
            full_name="Dup One",
            password="StrongPass123!",
            role=role_construction_manager,
        )
        with pytest.raises(IntegrityError):
            User.objects.create_user(
                email="dup@sflms.test",
                username="dupuser2",
                full_name="Dup Two",
                password="StrongPass123!",
                role=role_construction_manager,
            )
