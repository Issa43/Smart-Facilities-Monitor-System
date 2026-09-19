from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("assets", "0002_initial"),
        ("maintenance", "0003_lifecycle_constraints"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="maintenanceorder",
            name="maintenance_order_status_valid",
        ),
        migrations.RemoveConstraint(
            model_name="maintenanceorder",
            name="maintenance_cancellation_fields_valid",
        ),
        migrations.AddConstraint(
            model_name="maintenanceorder",
            constraint=models.CheckConstraint(
                check=models.Q(
                    ("status__in", ("open", "assigned", "in_progress", "completed", "closed", "cancelled"))
                ),
                name="maintenance_order_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="maintenanceorder",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(
                        ("status", "cancelled"),
                        ("cancelled_at__isnull", False),
                        ("cancelled_by__isnull", False),
                        models.Q(("cancellation_reason", ""), _negated=True),
                    ),
                    models.Q(
                        models.Q(("status", "cancelled"), _negated=True),
                        ("cancelled_at__isnull", True),
                        ("cancelled_by__isnull", True),
                        ("cancellation_reason", ""),
                    ),
                    _connector="OR",
                ),
                name="maintenance_cancellation_fields_valid",
            ),
        ),
    ]
