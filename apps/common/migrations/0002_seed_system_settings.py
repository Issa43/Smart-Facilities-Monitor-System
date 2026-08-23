from django.db import migrations


SETTINGS = {
    "notify.lowStock": True,
    "notify.overdueWorkOrders": True,
    "notify.criticalAlerts": True,
    "notify.stageReview": True,
    "security.sessionTimeout": True,
    "security.auditLog": True,
    "security.passwordPolicy": True,
    "workflow.requireApproval": True,
    "workflow.blockCompletion": True,
    "workflow.autoIncident": False,
}


def seed_settings(apps, schema_editor):
    SystemSetting = apps.get_model("common", "SystemSetting")
    for key, value in SETTINGS.items():
        SystemSetting.objects.get_or_create(key=key, defaults={"value": value})


class Migration(migrations.Migration):
    dependencies = [("common", "0001_systemsetting")]
    operations = [migrations.RunPython(seed_settings, migrations.RunPython.noop)]
