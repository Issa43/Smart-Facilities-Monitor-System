from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0002_execution_tasks_and_references")]
    operations = [
        migrations.AddConstraint(
            model_name="maintenanceorder",
            constraint=models.CheckConstraint(
                check=~models.Q(status__in=("completed", "closed")) | models.Q(actual_completion_date__isnull=False),
                name="maintenance_completed_has_date",
            ),
        ),
        migrations.AddConstraint(
            model_name="maintenanceorder",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(status="cancelled", cancelled_at__isnull=False, cancelled_by__isnull=False)
                    & ~models.Q(cancellation_reason="")
                ) | (
                    ~models.Q(status="cancelled")
                    & models.Q(cancelled_at__isnull=True, cancelled_by__isnull=True, cancellation_reason="")
                ),
                name="maintenance_cancellation_fields_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="maintenancetask",
            constraint=models.CheckConstraint(
                check=(models.Q(completed_at__isnull=True, completed_by__isnull=True) | models.Q(completed_at__isnull=False, completed_by__isnull=False)),
                name="maintenance_task_completion_fields_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="fault",
            constraint=models.CheckConstraint(
                check=~models.Q(status__in=("resolved", "closed")) | (
                    models.Q(root_cause__isnull=False)
                    & ~models.Q(root_cause="")
                    & models.Q(resolution__isnull=False)
                    & ~models.Q(resolution="")
                    & models.Q(resolved_at__isnull=False)
                ),
                name="fault_resolution_fields_valid",
            ),
        ),
    ]
