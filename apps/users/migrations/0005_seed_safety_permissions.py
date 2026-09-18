from django.db import migrations


SAFETY_PERMISSIONS = ("safety.view", "safety.manage", "safety.broadcast")
# Super Admin is intentionally not seeded: it bypasses permission checks.
GRANTS = {
    "construction_manager": SAFETY_PERMISSIONS,
    "operations_manager": SAFETY_PERMISSIONS,
}


def seed_safety_permissions(apps, schema_editor):
    Role = apps.get_model("users", "Role")
    Permission = apps.get_model("users", "Permission")
    for role_name, permission_names in GRANTS.items():
        role = Role.objects.filter(name=role_name).first()
        if role is None:
            continue
        for permission_name in permission_names:
            Permission.objects.get_or_create(role=role, permission_name=permission_name)


def remove_safety_permissions(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Permission.objects.filter(permission_name__in=SAFETY_PERMISSIONS).delete()


class Migration(migrations.Migration):
    dependencies = [("users", "0004_seed_role_permissions")]
    operations = [migrations.RunPython(seed_safety_permissions, remove_safety_permissions)]
