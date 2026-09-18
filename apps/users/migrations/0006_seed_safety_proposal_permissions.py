from django.db import migrations


# The two protective workflows are separate responsibilities, so they are
# separate grants. Neither manager receives the other's, and neither receives
# "safety.approve": that authority belongs to the General Manager, which
# `user_has_permission` resolves through the Super Admin break-glass branch
# rather than a stored grant.
GRANTS = {
    "construction_manager": ("safety.propose_worker_protection",),
    "operations_manager": ("safety.propose_asset_protection",),
}
SEEDED_PERMISSIONS = tuple(
    name for names in GRANTS.values() for name in names
)


def seed_proposal_permissions(apps, schema_editor):
    Role = apps.get_model("users", "Role")
    Permission = apps.get_model("users", "Permission")
    for role_name, permission_names in GRANTS.items():
        role = Role.objects.filter(name=role_name).first()
        if role is None:
            continue
        for permission_name in permission_names:
            Permission.objects.get_or_create(role=role, permission_name=permission_name)


def remove_proposal_permissions(apps, schema_editor):
    Permission = apps.get_model("users", "Permission")
    Permission.objects.filter(permission_name__in=SEEDED_PERMISSIONS).delete()


class Migration(migrations.Migration):
    dependencies = [("users", "0005_seed_safety_permissions")]
    operations = [
        migrations.RunPython(seed_proposal_permissions, remove_proposal_permissions)
    ]
