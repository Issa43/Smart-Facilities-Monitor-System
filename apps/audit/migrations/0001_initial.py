from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("action", models.CharField(max_length=100)),
                ("entity_type", models.CharField(max_length=100)),
                ("entity_id", models.CharField(max_length=100)),
                ("entity_ref", models.CharField(blank=True, default="", max_length=255)),
                ("before", models.JSONField(blank=True, null=True)),
                ("after", models.JSONField(blank=True, null=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, default="", max_length=500)),
                ("request_id", models.UUIDField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="audit_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"], "indexes": [models.Index(fields=["actor", "-created_at"], name="audit_actor_time_idx"), models.Index(fields=["entity_type", "entity_id", "-created_at"], name="audit_entity_time_idx"), models.Index(fields=["action", "-created_at"], name="audit_action_time_idx")]},
        )
    ]
