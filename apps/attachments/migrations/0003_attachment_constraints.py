from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("attachments", "0002_alter_attachment_entity_type")]
    operations = [
        migrations.AddConstraint(
            model_name="attachment",
            constraint=models.CheckConstraint(
                check=models.Q(("entity_type__in", ("project_phase", "phase_progress_log", "daily_report", "material_request", "material_consumption_record", "incident", "incident_action"))),
                name="attachment_entity_type_allowed",
            ),
        ),
        migrations.AddConstraint(
            model_name="attachment",
            constraint=models.CheckConstraint(check=models.Q(("file_size__gt", 0)), name="attachment_file_size_gt_zero"),
        ),
    ]
