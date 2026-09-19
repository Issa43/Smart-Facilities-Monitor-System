from django.db import migrations


# External safety alerting ships disabled. An empty policy override means the
# built-in illustrative defaults in apps/safety/policy.py apply once enabled.
SETTINGS = {
    "safety.externalAlerts": (
        False,
        "Allow external hazard events to create project safety alerts.",
    ),
    "notify.safetyAlerts": (
        True,
        "Notify responsible managers about project safety alerts.",
    ),
    "safety.hazardPolicy": (
        {},
        "Validated per-hazard overrides for the external safety alert policy.",
    ),
}


def seed_safety_settings(apps, schema_editor):
    SystemSetting = apps.get_model("common", "SystemSetting")
    for key, (value, description) in SETTINGS.items():
        SystemSetting.objects.get_or_create(
            key=key,
            defaults={"value": value, "description": description},
        )


def remove_safety_settings(apps, schema_editor):
    SystemSetting = apps.get_model("common", "SystemSetting")
    SystemSetting.objects.filter(key__in=SETTINGS).delete()


class Migration(migrations.Migration):
    dependencies = [("common", "0002_seed_system_settings")]
    operations = [migrations.RunPython(seed_safety_settings, remove_safety_settings)]
