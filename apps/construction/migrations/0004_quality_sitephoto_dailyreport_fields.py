from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
import apps.attachments.storage
import apps.attachments.validators
import apps.construction.models
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("construction", "0003_dailyreport_daily_report_creator_required"),
        ("projects", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(model_name="dailyreport", name="title", field=models.CharField(blank=True, default="", max_length=255)),
        migrations.AddField(model_name="dailyreport", name="progress_percentage", field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=5, validators=[django.core.validators.MinValueValidator(Decimal("0")), django.core.validators.MaxValueValidator(Decimal("100"))])),
        migrations.CreateModel(
            name="QualityInspection",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("is_active", models.BooleanField(default=True)),
                ("title", models.CharField(max_length=255)),
                ("score", models.DecimalField(decimal_places=2, max_digits=5, validators=[django.core.validators.MinValueValidator(Decimal("0")), django.core.validators.MaxValueValidator(Decimal("100"))])),
                ("result", models.CharField(choices=[("passed", "Passed"), ("passed_with_notes", "Passed with notes"), ("failed", "Failed")], max_length=20)),
                ("notes", models.TextField(blank=True, default="")), ("inspected_at", models.DateTimeField()),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("inspector", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="quality_inspections", to=settings.AUTH_USER_MODEL)),
                ("phase", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="quality_inspections", to="projects.projectphase")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="quality_inspections", to="projects.project")),
            ],
            options={"ordering": ["-created_at"], "indexes": [models.Index(fields=["project", "-inspected_at"], name="quality_project_time_idx"), models.Index(fields=["phase", "result"], name="quality_phase_result_idx")], "constraints": [models.CheckConstraint(check=models.Q(("score__gte", 0), ("score__lte", 100)), name="quality_score_range")]},
        ),
        migrations.CreateModel(
            name="SitePhoto",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("is_active", models.BooleanField(default=True)),
                ("image", models.ImageField(storage=apps.attachments.storage.get_protected_storage, upload_to=apps.construction.models.site_photo_upload_path, validators=[apps.attachments.validators.validate_attachment_file])),
                ("caption", models.CharField(max_length=500)), ("captured_at", models.DateTimeField()),
                ("original_file_name", models.CharField(max_length=255)), ("mime_type", models.CharField(max_length=127)), ("file_size", models.PositiveBigIntegerField()),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("phase", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="site_photos", to="projects.projectphase")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="site_photos", to="projects.project")),
            ],
            options={"ordering": ["-created_at"], "indexes": [models.Index(fields=["project", "-captured_at"], name="site_photo_project_time_idx"), models.Index(fields=["phase", "-captured_at"], name="site_photo_phase_time_idx")], "constraints": [models.CheckConstraint(check=models.Q(("file_size__gt", 0)), name="site_photo_size_positive")]},
        ),
    ]
