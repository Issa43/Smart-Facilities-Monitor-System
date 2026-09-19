import os

# Sanitize the environment before Django or Celery is imported below.
#
# Celery does not read its broker from Django settings alone: ``Settings.
# broker_url`` returns ``os.environ['CELERY_BROKER_URL']`` first and only then
# falls back to the configured value. The containers export
# CELERY_BROKER_URL=redis://redis:6379/0, so a test process inherited the
# development broker even under config.settings.test. Overriding the variables
# here — while the test process is the only thing affected — is the only place
# that closes it.
# All four env-first settings, not just the two the containers happen to set
# today, so a later compose change cannot quietly reopen the hole.
os.environ["CELERY_BROKER_URL"] = "memory://"
os.environ["CELERY_BROKER_READ_URL"] = "memory://"
os.environ["CELERY_BROKER_WRITE_URL"] = "memory://"
os.environ["CELERY_RESULT_BACKEND"] = "cache+memory://"

import socket  # noqa: E402

import pytest  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from apps.users.models import Permission, Role, User  # noqa: E402


# ---------------------------------------------------------------------------
# Test runtime isolation
#
# A test run must not be able to reach real infrastructure, whatever the
# environment says. A suite once inherited DJANGO_SETTINGS_MODULE=
# config.settings.development from its container, ran without eager Celery, and
# published tasks to the development Redis broker. The guards below make that
# fail loudly instead of silently succeeding.
# ---------------------------------------------------------------------------

EXPECTED_SETTINGS_MODULE = "config.settings.test"
SAFE_TEST_BROKERS = ("memory://",)
# Loopback only: the Django test client and any local helper server stay usable,
# while every external host — Telegram, USGS, GDACS, FCM, Redis, PostgreSQL —
# is refused.
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1", "::", ""})

_real_socket_connect = socket.socket.connect
_real_socket_connect_ex = socket.socket.connect_ex
_real_create_connection = socket.create_connection


class ExternalNetworkBlocked(RuntimeError):
    """Raised when a test tries to open a connection outside the test process."""


def _is_loopback(address):
    if not isinstance(address, (tuple, list)) or not address:
        # AF_UNIX paths and other families are not an external network hop.
        return True
    host = address[0]
    if isinstance(host, bytes):
        host = host.decode("utf-8", "replace")
    host = str(host)
    return host in LOOPBACK_HOSTS or host.startswith("127.")


def _guard(address):
    if not _is_loopback(address):
        raise ExternalNetworkBlocked(
            f"Tests may not open external connections (attempted {address!r}). "
            "Mock the client instead; see conftest.py."
        )


def _guarded_connect(self, address):
    _guard(address)
    return _real_socket_connect(self, address)


def _guarded_connect_ex(self, address):
    _guard(address)
    return _real_socket_connect_ex(self, address)


def _guarded_create_connection(address, *args, **kwargs):
    _guard(address)
    return _real_create_connection(address, *args, **kwargs)


def pytest_configure(config):
    """Fail closed before a single test runs if the runtime is not isolated."""

    from django.conf import settings

    if settings.SETTINGS_MODULE != EXPECTED_SETTINGS_MODULE:
        raise pytest.UsageError(
            f"Tests must run under {EXPECTED_SETTINGS_MODULE}, got "
            f"{settings.SETTINGS_MODULE!r}. The environment's "
            "DJANGO_SETTINGS_MODULE outranks pytest.ini's ini value, so "
            "pytest.ini passes --ds through addopts; do not remove it."
        )
    if not getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        raise pytest.UsageError(
            "CELERY_TASK_ALWAYS_EAGER must be on in tests; otherwise .delay() "
            "publishes to a real broker."
        )
    broker = str(getattr(settings, "CELERY_BROKER_URL", "") or "")
    if not broker.startswith(SAFE_TEST_BROKERS):
        raise pytest.UsageError(
            f"Tests must use an in-process Celery broker, got {broker!r}. "
            "A development or production broker is never acceptable here."
        )
    # Checked separately: Celery resolves its broker from the environment
    # first, so the Django setting agreeing is not proof that Celery agrees.
    from config.celery import app as celery_app

    effective_broker = str(celery_app.conf.broker_url or "")
    if not effective_broker.startswith(SAFE_TEST_BROKERS):
        raise pytest.UsageError(
            f"Celery resolved broker {effective_broker!r}. Its Settings."
            "broker_url reads os.environ['CELERY_BROKER_URL'] ahead of Django "
            "settings; conftest.py neutralizes it, so do not remove that."
        )
    # Applied at configure time so module-import side effects are covered too.
    socket.socket.connect = _guarded_connect
    socket.socket.connect_ex = _guarded_connect_ex
    socket.create_connection = _guarded_create_connection


def pytest_unconfigure(config):
    socket.socket.connect = _real_socket_connect
    socket.socket.connect_ex = _real_socket_connect_ex
    socket.create_connection = _real_create_connection


ROLE_FIXTURES = {
    Role.SUPER_ADMIN: {
        "description": "Full, unrestricted access to every module in the system.",
        "permissions": {
            "project.create", "project.edit", "project.view", "project.close",
            "material.stock", "alert.view", "report.generate", "report.all",
            "user.manage", "role.manage", "audit.view", "settings.manage",
        },
    },
    Role.CONSTRUCTION_MANAGER: {
        "description": "Access limited to assigned projects and construction modules.",
        "permissions": {
            "project.edit", "project.view", "project.close", "stage.create",
            "stage.edit", "stage.delete", "stage.progress", "stage.approve",
            "material.manage", "material.request", "material.stock", "report.generate",
            "safety.view", "safety.manage", "safety.broadcast",
        },
    },
    Role.OPERATIONS_MANAGER: {
        "description": "Access limited to assigned facilities and operations modules.",
        "permissions": {
            "asset.manage", "asset.status", "workorder.create", "workorder.close",
            "fault.manage", "incident.update", "report.generate",
            "safety.view", "safety.manage", "safety.broadcast",
        },
    },
    Role.SECURITY_OFFICER: {
        "description": "Access limited to assigned facilities and security modules.",
        "permissions": {
            "alert.view", "incident.create", "incident.update", "incident.close",
            "incident.escalate", "report.generate",
        },
    },
}


def seeded_role(name):
    """Restore fixed RBAC reference data after transactional test database flushes."""

    roles = {}
    for role_name, fixture in ROLE_FIXTURES.items():
        role, _ = Role.objects.get_or_create(
            name=role_name,
            defaults={"description": fixture["description"]},
        )
        roles[role_name] = role
        for permission_name in fixture["permissions"]:
            Permission.objects.get_or_create(
                role=role,
                permission_name=permission_name,
            )
    return roles[name]


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def role_super_admin(db):
    return seeded_role(Role.SUPER_ADMIN)


@pytest.fixture
def role_construction_manager(db):
    return seeded_role(Role.CONSTRUCTION_MANAGER)


@pytest.fixture
def role_operations_manager(db):
    return seeded_role(Role.OPERATIONS_MANAGER)


@pytest.fixture
def role_security_officer(db):
    return seeded_role(Role.SECURITY_OFFICER)


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
