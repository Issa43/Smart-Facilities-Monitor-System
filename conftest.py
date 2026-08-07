import pytest
from rest_framework.test import APIClient

from apps.users.models import Role, User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def role_super_admin(db):
    return Role.objects.get(name=Role.SUPER_ADMIN)


@pytest.fixture
def role_construction_manager(db):
    return Role.objects.get(name=Role.CONSTRUCTION_MANAGER)


@pytest.fixture
def role_operations_manager(db):
    return Role.objects.get(name=Role.OPERATIONS_MANAGER)


@pytest.fixture
def role_security_officer(db):
    return Role.objects.get(name=Role.SECURITY_OFFICER)


@pytest.fixture
def super_admin_user(db, role_super_admin):
    return User.objects.create_user(
        email="admin@sflms.test",
        username="superadmin",
        full_name="Super Admin",
        password="StrongPass123!",
        role=role_super_admin,
        status=User.STATUS_ACTIVE,
    )


@pytest.fixture
def construction_manager_user(db, role_construction_manager):
    return User.objects.create_user(
        email="cm@sflms.test",
        username="cmanager",
        full_name="Construction Manager",
        password="StrongPass123!",
        role=role_construction_manager,
        status=User.STATUS_ACTIVE,
    )


@pytest.fixture
def suspended_user(db, role_operations_manager):
    return User.objects.create_user(
        email="suspended@sflms.test",
        username="suspendeduser",
        full_name="Suspended User",
        password="StrongPass123!",
        role=role_operations_manager,
        status=User.STATUS_SUSPENDED,
    )


@pytest.fixture
def authenticated_client(api_client, super_admin_user):
    api_client.force_authenticate(user=super_admin_user)
    return api_client
