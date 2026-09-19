from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid
import apps.maintenance.models


def populate_references(apps, schema_editor):
    Order = apps.get_model("maintenance", "MaintenanceOrder")
    for order in Order.objects.filter(reference__isnull=True).iterator():
        order.reference = f"WO-{uuid.uuid4().hex[:12].upper()}"
        order.save(update_fields=["reference"])


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name="maintenanceorder", name="reference", field=models.CharField(blank=True, max_length=20, null=True)),
        migrations.RunPython(populate_references, migrations.RunPython.noop),
        migrations.AlterField(model_name="maintenanceorder", name="reference", field=models.CharField(default=apps.maintenance.models.generate_maintenance_reference, editable=False, max_length=20, unique=True)),
        migrations.AddField(model_name="maintenanceorder", name="execution_notes", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="maintenanceorder", name="cancelled_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="maintenanceorder", name="cancellation_reason", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="maintenanceorder", name="cancelled_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="cancelled_maintenance_orders", to=settings.AUTH_USER_MODEL)),
        migrations.AlterField(model_name="maintenanceorder", name="status", field=models.CharField(choices=[("open", "Open"), ("assigned", "Assigned"), ("in_progress", "In Progress"), ("completed", "Completed"), ("closed", "Closed"), ("cancelled", "Cancelled")], default="open", max_length=20)),
        migrations.AddField(model_name="fault", name="resolved_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.CreateModel(
            name="MaintenanceTask",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("is_active", models.BooleanField(default=True)),
                ("sequence", models.PositiveIntegerField()), ("label", models.CharField(max_length=255)), ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("completed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="completed_maintenance_tasks", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="tasks", to="maintenance.maintenanceorder")),
            ],
            options={"ordering": ["sequence"], "indexes": [models.Index(fields=["order", "sequence"], name="maint_task_order_seq_idx")], "constraints": [models.UniqueConstraint(fields=("order", "sequence"), name="unique_maintenance_task_sequence")]},
        ),
    ]
