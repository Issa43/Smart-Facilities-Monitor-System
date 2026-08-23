from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("projects", "0001_initial")]
    operations = [
        migrations.RemoveConstraint(
            model_name="projectphase",
            name="phase_priority_valid",
        ),
        migrations.AlterField(
            model_name="projectphase",
            name="priority",
            field=models.CharField(
                choices=[
                    ("low", "Low"),
                    ("medium", "Medium"),
                    ("high", "High"),
                    ("critical", "Critical"),
                ],
                default="medium",
                max_length=10,
            ),
        ),
        migrations.AddConstraint(
            model_name="projectphase",
            constraint=models.CheckConstraint(
                check=models.Q(priority__in=("low", "medium", "high", "critical")),
                name="phase_priority_valid",
            ),
        ),
    ]
