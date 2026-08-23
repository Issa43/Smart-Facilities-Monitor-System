from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="NotificationPreference",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("low_stock", models.BooleanField(default=True)),
                ("overdue_work_orders", models.BooleanField(default=True)),
                ("critical_alerts", models.BooleanField(default=True)),
                ("stage_review", models.BooleanField(default=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="notification_preference", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("title", models.CharField(max_length=255)),
                ("body", models.TextField()),
                ("category", models.CharField(choices=[("project", "Project"), ("material", "Material"), ("maintenance", "Maintenance"), ("security", "Security"), ("system", "System")], max_length=20)),
                ("tone", models.CharField(choices=[("neutral", "Neutral"), ("info", "Info"), ("success", "Success"), ("warning", "Warning"), ("critical", "Critical")], default="info", max_length=10)),
                ("href", models.CharField(blank=True, max_length=500, null=True)),
                ("source_type", models.CharField(blank=True, max_length=64, null=True)),
                ("source_id", models.UUIDField(blank=True, null=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [models.Index(fields=["recipient", "read_at", "-created_at"], name="notif_recipient_read_idx"), models.Index(fields=["source_type", "source_id"], name="notif_source_idx")],
                "constraints": [models.CheckConstraint(check=models.Q(("title", ""), _negated=True), name="notification_title_required"), models.CheckConstraint(check=models.Q(("body", ""), _negated=True), name="notification_body_required")],
            },
        ),
    ]
