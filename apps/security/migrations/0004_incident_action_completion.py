from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("security", "0003_cameras_notes_and_safety_documents"),
    ]
    operations = [
        migrations.AddField(
            model_name="incidentaction",
            name="completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="incidentaction",
            name="completed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="completed_incident_actions",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="incidentaction",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(completed_at__isnull=True, completed_by__isnull=True)
                    | models.Q(completed_at__isnull=False, completed_by__isnull=False)
                ),
                name="incident_action_completion_fields_valid",
            ),
        ),
    ]
