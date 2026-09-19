from django.db import migrations


GRANTS = {
    "super_admin": [
        "project.create", "project.edit", "project.view", "project.close",
        "material.stock", "alert.view", "report.generate", "report.all",
        "user.manage", "role.manage", "audit.view", "settings.manage",
    ],
    "construction_manager": [
        "project.edit", "project.view", "project.close", "stage.create",
        "stage.edit", "stage.delete", "stage.progress", "stage.approve",
        "material.manage", "material.request", "material.stock", "report.generate",
    ],
    "operations_manager": [
        "asset.manage", "asset.status", "workorder.create", "workorder.close",
        "fault.manage", "incident.update", "report.generate",
    ],
    "security_officer": [
        "alert.view", "incident.create", "incident.update", "incident.close",
        "incident.escalate", "report.generate",
    ],
}


def seed_permissions(apps, schema_editor):
    Role = apps.get_model("users", "Role")
    Permission = apps.get_model("users", "Permission")
    for role_name, permission_names in GRANTS.items():
        role = Role.objects.get(name=role_name)
        for permission_name in permission_names:
            Permission.objects.get_or_create(
                role=role,
                permission_name=permission_name,
            )


def remove_seeded_permissions(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Permission.objects.filter(
        permission_name__in={name for names in GRANTS.values() for name in names}
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("users", "0003_rename_users_user_email_idx_users_user_email_6f2530_idx_and_more")]
    operations = [migrations.RunPython(seed_permissions, remove_seeded_permissions)]
