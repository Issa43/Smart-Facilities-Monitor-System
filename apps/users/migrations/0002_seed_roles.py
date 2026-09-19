from django.db import migrations

ROLES = [
    ("super_admin", "Full, unrestricted access to every module in the system."),
    ("construction_manager", "Access limited to assigned projects and construction modules."),
    ("operations_manager", "Access limited to assigned facilities and operations modules."),
    ("security_officer", "Access limited to assigned facilities and security modules."),
]


def seed_roles(apps, schema_editor):
    Role = apps.get_model("users", "Role")
    for name, description in ROLES:
        Role.objects.get_or_create(name=name, defaults={"description": description})


def unseed_roles(apps, schema_editor):
    Role = apps.get_model("users", "Role")
    Role.objects.filter(name__in=[name for name, _ in ROLES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_roles, unseed_roles),
    ]
