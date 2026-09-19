import uuid

import apps.maintenance.models
from django.db import migrations, models


def populate_fault_references(apps, schema_editor):
    Fault = apps.get_model("maintenance", "Fault")
    for fault in Fault.objects.filter(reference__isnull=True).iterator():
        fault.reference = f"FLT-{uuid.uuid4().hex[:12].upper()}"
        fault.save(update_fields=["reference"])


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0004_sync_lifecycle_constraints")]

    operations = [
        migrations.AddField(
            model_name="fault",
            name="reference",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.RunPython(populate_fault_references, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="fault",
            name="reference",
            field=models.CharField(
                default=apps.maintenance.models.generate_fault_reference,
                editable=False,
                max_length=20,
                unique=True,
            ),
        ),
    ]
