import importlib

import pytest
from django.apps import apps as django_apps

from apps.common.models import SystemSetting
from apps.safety.tests.helpers import make_user, set_setting
from apps.users.models import Permission, Role
from apps.users.permissions import PERMISSION_CATALOG


pytestmark = pytest.mark.django_db

SAFETY_PERMISSIONS = {"safety.view", "safety.manage", "safety.broadcast"}


def _patch(client, key, value, version):
    return client.patch(f"/api/v1/settings/{key}/", {"value": value, "version": version}, format="json")


def _migration(name):
    return importlib.import_module(name)


def test_migrations_seed_disabled_safety_settings():
    module = _migration("apps.common.migrations.0003_seed_safety_settings")
    SystemSetting.objects.filter(key__in=module.SETTINGS).delete()
    module.seed_safety_settings(django_apps, None)
    module.seed_safety_settings(django_apps, None)
    values = dict(
        SystemSetting.objects.filter(
            key__in=["safety.externalAlerts", "notify.safetyAlerts", "safety.hazardPolicy"]
        ).values_list("key", "value")
    )
    assert values == {
        "safety.externalAlerts": False,
        "notify.safetyAlerts": True,
        "safety.hazardPolicy": {},
    }


def test_migrations_grant_safety_permissions_to_managers_only():
    module = _migration("apps.users.migrations.0005_seed_safety_permissions")
    for role_name in (Role.SUPER_ADMIN, Role.CONSTRUCTION_MANAGER, Role.OPERATIONS_MANAGER, Role.SECURITY_OFFICER):
        Role.objects.get_or_create(name=role_name)
    Permission.objects.filter(permission_name__in=SAFETY_PERMISSIONS).delete()
    module.seed_safety_permissions(django_apps, None)
    module.seed_safety_permissions(django_apps, None)
    granted = set(
        Permission.objects.filter(permission_name__in=SAFETY_PERMISSIONS).values_list(
            "role__name", "permission_name"
        )
    )
    assert granted == {
        (role, permission)
        for role in (Role.CONSTRUCTION_MANAGER, Role.OPERATIONS_MANAGER)
        for permission in SAFETY_PERMISSIONS
    }
    assert SAFETY_PERMISSIONS <= PERMISSION_CATALOG

    module.remove_safety_permissions(django_apps, None)
    assert not Permission.objects.filter(permission_name__in=SAFETY_PERMISSIONS).exists()


def test_settings_seed_is_reversible():
    module = _migration("apps.common.migrations.0003_seed_safety_settings")
    module.seed_safety_settings(django_apps, None)
    module.remove_safety_settings(django_apps, None)
    assert not SystemSetting.objects.filter(key__in=module.SETTINGS).exists()


def test_invalid_policy_override_is_rejected_by_settings_api(api_client, super_admin_user):
    setting = set_setting("safety.hazardPolicy", {})
    api_client.force_authenticate(super_admin_user)

    response = _patch(
        api_client,
        "safety.hazardPolicy",
        {"hazards": {"earthquake": {"tiers": [{"min_magnitude": 5, "radius_km": 5000, "severity": "high", "recommended_action": "monitor"}]}}},
        setting.version,
    )

    assert response.status_code == 400
    assert response.data["success"] is False
    setting.refresh_from_db()
    assert setting.value == {} and setting.version == 1


def test_valid_policy_override_is_saved_and_versioned(api_client, super_admin_user):
    setting = set_setting("safety.hazardPolicy", {})
    api_client.force_authenticate(super_admin_user)
    override = {"hazards": {"flood": {"max_event_age_hours": 24}}}

    response = _patch(api_client, "safety.hazardPolicy", override, setting.version)

    assert response.status_code == 200
    setting.refresh_from_db()
    assert setting.value == override and setting.version == 2


def test_boolean_safety_settings_reject_non_boolean_values(api_client, super_admin_user):
    setting = set_setting("safety.externalAlerts", False)
    api_client.force_authenticate(super_admin_user)
    response = _patch(api_client, "safety.externalAlerts", "true", setting.version)
    assert response.status_code == 400

    created = api_client.post(
        "/api/v1/settings/",
        {"key": "notify.safetyAlerts-shadow", "value": "anything"},
        format="json",
    )
    assert created.status_code == 201


def test_boolean_safety_setting_cannot_be_created_with_wrong_type(api_client, super_admin_user):
    SystemSetting.objects.filter(key="notify.safetyAlerts").delete()
    api_client.force_authenticate(super_admin_user)
    response = api_client.post(
        "/api/v1/settings/",
        {"key": "notify.safetyAlerts", "value": "yes"},
        format="json",
    )
    assert response.status_code == 400
    assert not SystemSetting.objects.filter(key="notify.safetyAlerts").exists()


def test_non_admin_cannot_change_safety_settings(api_client):
    manager = make_user(Role.OPERATIONS_MANAGER, "om")
    setting = set_setting("safety.externalAlerts", False)
    api_client.force_authenticate(manager)
    response = _patch(api_client, "safety.externalAlerts", True, setting.version)
    assert response.status_code == 403
    setting.refresh_from_db()
    assert setting.value is False


def test_unrelated_settings_keep_existing_behavior(api_client, super_admin_user):
    setting = set_setting("notify.lowStock", True)
    api_client.force_authenticate(super_admin_user)
    response = _patch(api_client, "notify.lowStock", not setting.value, setting.version)
    assert response.status_code == 200
