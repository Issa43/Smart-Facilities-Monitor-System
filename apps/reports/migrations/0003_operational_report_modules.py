from django.conf import settings
from django.db import migrations, models


MODULES = (
    "projects", "construction", "materials", "assets", "maintenance",
    "faults", "operational_performance", "security", "users", "alerts",
    "response",
)
CHOICES = [
    ("projects", "Projects"), ("construction", "Construction"),
    ("materials", "Materials"), ("assets", "Assets"),
    ("maintenance", "Maintenance"), ("faults", "Faults"),
    ("operational_performance", "Operational performance"),
    ("security", "Security"), ("users", "Users"),
    ("alerts", "Security alerts"), ("response", "Incident response"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0002_extended_report_modules"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="report", name="report_module_valid"),
        migrations.RemoveConstraint(model_name="reporttemplate", name="report_template_module_valid"),
        migrations.AlterField(model_name="report", name="module", field=models.CharField(choices=CHOICES, max_length=32)),
        migrations.AlterField(model_name="reporttemplate", name="module", field=models.CharField(choices=CHOICES, max_length=32)),
        migrations.AddConstraint(model_name="report", constraint=models.CheckConstraint(check=models.Q(module__in=MODULES), name="report_module_valid")),
        migrations.AddConstraint(model_name="reporttemplate", constraint=models.CheckConstraint(check=models.Q(module__in=MODULES), name="report_template_module_valid")),
    ]
