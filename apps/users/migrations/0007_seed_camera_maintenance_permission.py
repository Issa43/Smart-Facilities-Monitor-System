from django.db import migrations


# Security Officers may only report a camera that needs maintenance. The Fault
# they raise is then worked through the Operations Manager's existing
# fault.manage / workorder.* authority, which this grant does not include.
GRANTS = {"security_officer": ("camera.maintenance_report",)}
SEEDED_PERMISSIONS = tuple(
    name for names in GRANTS.values() for name in names
)


def seed_camera_permissions(apps, schema_editor):
    Role = apps.get_model("users", "Role")
    Permission = apps.get_model("users", "Permission")
    for role_name, permission_names in GRANTS.items():
        role = Role.objects.filter(name=role_name).first()
        if role is None:
            continue
        for permission_name in permission_names:
            Permission.objects.get_or_create(role=role, permission_name=permission_name)


def remove_camera_permissions(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Permission.objects.filter(permission_name__in=SEEDED_PERMISSIONS).delete()


class Migration(migrations.Migration):
    dependencies = [("users", "0006_seed_safety_proposal_permissions")]
    operations = [
        migrations.RunPython(seed_camera_permissions, remove_camera_permissions)
    ]
