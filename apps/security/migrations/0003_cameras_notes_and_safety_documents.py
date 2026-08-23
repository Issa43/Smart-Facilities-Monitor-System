from django.conf import settings
from django.db import migrations, models
import apps.attachments.storage
import apps.attachments.validators
import apps.security.models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("security", "0002_remove_securityalert_security_alert_type_valid_and_more"),
        ("assets", "0002_initial"),
        ("facilities", "0004_facility_operation_start_date"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="IncidentNote",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("is_active", models.BooleanField(default=True)),
                ("body", models.TextField()),
                ("author", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="security_incident_notes", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("incident", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="notes", to="security.incident")),
            ],
            options={"ordering": ["-created_at"], "indexes": [models.Index(fields=["incident", "-created_at"], name="incident_note_time_idx")], "constraints": [models.CheckConstraint(check=models.Q(("body", ""), _negated=True), name="incident_note_body_required")]},
        ),
        migrations.CreateModel(
            name="Camera",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("is_active", models.BooleanField(default=True)),
                ("code", models.CharField(max_length=100, unique=True)), ("name", models.CharField(max_length=255)), ("zone", models.CharField(max_length=255)),
                ("stream_reference", models.CharField(blank=True, default="", max_length=500)),
                ("status", models.CharField(choices=[("online", "Online"), ("offline", "Offline"), ("degraded", "Degraded"), ("maintenance", "Maintenance")], default="offline", max_length=20)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                ("asset", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="cameras", to="assets.asset")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("facility", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cameras", to="facilities.facility")),
            ],
            options={"ordering": ["-created_at"], "indexes": [models.Index(fields=["facility", "status"], name="camera_facility_status_idx"), models.Index(fields=["-last_seen_at"], name="camera_last_seen_idx")]},
        ),
        migrations.CreateModel(
            name="SafetyDocument",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("is_active", models.BooleanField(default=True)),
                ("title", models.CharField(max_length=255)),
                ("category", models.CharField(choices=[("policy", "Policy"), ("procedure", "Procedure"), ("permit", "Permit"), ("report", "Report")], max_length=20)),
                ("file", models.FileField(storage=apps.attachments.storage.get_protected_storage, upload_to=apps.security.models.safety_document_upload_path, validators=[apps.attachments.validators.validate_attachment_file])),
                ("original_file_name", models.CharField(max_length=255)), ("mime_type", models.CharField(max_length=127)), ("file_size", models.PositiveBigIntegerField()),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("facility", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="safety_documents", to="facilities.facility")),
            ],
            options={"ordering": ["-created_at"], "indexes": [models.Index(fields=["facility", "category", "-created_at"], name="safety_doc_fac_cat_idx")], "constraints": [models.CheckConstraint(check=models.Q(("file_size__gt", 0)), name="safety_document_size_positive")]},
        ),
    ]
