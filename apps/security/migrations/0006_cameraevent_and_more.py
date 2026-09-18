import apps.attachments.storage
import django.core.validators
import django.db.models.deletion
import uuid
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("facilities", "0004_facility_operation_start_date"),
        ("security", "0005_ai_ingestion_credentials"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CameraEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("event_type", models.CharField(choices=[("fire_alert", "Fire alert"), ("smoke_alert", "Smoke alert"), ("intrusion_alert", "Intrusion alert"), ("vehicle_entry", "Vehicle entry"), ("vehicle_exit", "Vehicle exit"), ("tamper_alert", "Tamper alert")], max_length=30)),
                ("source_event_id", models.UUIDField()),
                ("track_id", models.CharField(blank=True, max_length=255, null=True)),
                ("confidence", models.DecimalField(blank=True, decimal_places=6, max_digits=7, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0")), django.core.validators.MaxValueValidator(Decimal("1"))])),
                ("object_class", models.CharField(blank=True, max_length=100, null=True)),
                ("detected_at", models.DateTimeField()),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("duration_seconds", models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("snapshot_path", models.FileField(blank=True, max_length=500, null=True, storage=apps.attachments.storage.get_protected_storage, upload_to="")),
                ("bbox", models.JSONField(blank=True, null=True)),
                ("bbox_plate", models.JSONField(blank=True, null=True)),
                ("bbox_vehicle", models.JSONField(blank=True, null=True)),
                ("crossing_centroid", models.JSONField(blank=True, null=True)),
                ("entered_roi_at", models.DateTimeField(blank=True, null=True)),
                ("time_restricted", models.BooleanField(blank=True, null=True)),
                ("plate_number", models.CharField(blank=True, max_length=32, null=True)),
                ("plate_confidence", models.DecimalField(blank=True, decimal_places=6, max_digits=7, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0")), django.core.validators.MaxValueValidator(Decimal("1"))])),
                ("ocr_confidence", models.DecimalField(blank=True, decimal_places=6, max_digits=7, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0")), django.core.validators.MaxValueValidator(Decimal("1"))])),
                ("vehicle_type", models.CharField(blank=True, choices=[("car", "Car"), ("truck", "Truck"), ("van", "Van"), ("bus", "Bus"), ("motorcycle", "Motorcycle")], max_length=20, null=True)),
                ("vehicle_confidence", models.DecimalField(blank=True, decimal_places=6, max_digits=7, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0")), django.core.validators.MaxValueValidator(Decimal("1"))])),
                ("direction", models.CharField(blank=True, choices=[("entry", "Entry"), ("exit", "Exit")], max_length=10, null=True)),
                ("authorized", models.BooleanField(blank=True, null=True)),
                ("tamper_type", models.CharField(blank=True, choices=[("camera_covered", "Camera covered"), ("camera_moved", "Camera moved"), ("signal_lost", "Signal lost"), ("out_of_focus", "Out of focus")], max_length=30, null=True)),
            ],
            options={"ordering": ["-created_at"], "abstract": False},
        ),
        migrations.RemoveConstraint(
            model_name="securityalert",
            name="security_alert_type_valid",
        ),
        migrations.AlterField(
            model_name="securityalert",
            name="alert_type",
            field=models.CharField(choices=[("fire", "Fire"), ("smoke", "Smoke"), ("intrusion", "Intrusion"), ("motion", "Motion"), ("unauthorized_person", "Unauthorized Person"), ("emergency", "Emergency"), ("vehicle", "Vehicle"), ("tamper", "Tamper")], max_length=20),
        ),
        migrations.AddConstraint(
            model_name="securityalert",
            constraint=models.CheckConstraint(check=models.Q(("alert_type__in", ("fire", "smoke", "intrusion", "motion", "unauthorized_person", "emergency", "vehicle", "tamper"))), name="security_alert_type_valid"),
        ),
        migrations.AddField(
            model_name="cameraevent",
            name="camera",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="events", to="security.camera"),
        ),
        migrations.AddField(
            model_name="cameraevent",
            name="created_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="cameraevent",
            name="ingestion_credential",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="camera_events", to="security.aiingestioncredential"),
        ),
        migrations.AddField(
            model_name="cameraevent",
            name="security_alert",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="camera_event", to="security.securityalert"),
        ),
        migrations.AddIndex(model_name="cameraevent", index=models.Index(fields=["camera", "-detected_at"], name="cam_event_cam_detect_idx")),
        migrations.AddIndex(model_name="cameraevent", index=models.Index(fields=["event_type", "-detected_at"], name="cam_event_type_detect_idx")),
        migrations.AddIndex(model_name="cameraevent", index=models.Index(fields=["plate_number", "-detected_at"], name="cam_event_plate_detect_idx")),
        migrations.AddIndex(model_name="cameraevent", index=models.Index(fields=["authorized", "event_type", "-detected_at"], name="cam_event_auth_type_det_idx")),
        migrations.AddIndex(model_name="cameraevent", index=models.Index(fields=["tamper_type", "-detected_at"], name="cam_event_tamp_detect_idx")),
        migrations.AddConstraint(model_name="cameraevent", constraint=models.UniqueConstraint(fields=("ingestion_credential", "source_event_id"), name="unique_cam_event_source")),
        migrations.AddConstraint(model_name="cameraevent", constraint=models.CheckConstraint(check=models.Q(("event_type__in", ("fire_alert", "smoke_alert", "intrusion_alert", "vehicle_entry", "vehicle_exit", "tamper_alert"))), name="cam_event_type_valid")),
        migrations.AddConstraint(model_name="cameraevent", constraint=models.CheckConstraint(check=models.Q(("confidence__isnull", True), models.Q(("confidence__gte", 0), ("confidence__lte", 1)), _connector="OR"), name="cam_event_confidence_range")),
        migrations.AddConstraint(model_name="cameraevent", constraint=models.CheckConstraint(check=models.Q(("plate_confidence__isnull", True), models.Q(("plate_confidence__gte", 0), ("plate_confidence__lte", 1)), _connector="OR"), name="cam_event_plate_conf_range")),
        migrations.AddConstraint(model_name="cameraevent", constraint=models.CheckConstraint(check=models.Q(("ocr_confidence__isnull", True), models.Q(("ocr_confidence__gte", 0), ("ocr_confidence__lte", 1)), _connector="OR"), name="cam_event_ocr_conf_range")),
        migrations.AddConstraint(model_name="cameraevent", constraint=models.CheckConstraint(check=models.Q(("vehicle_confidence__isnull", True), models.Q(("vehicle_confidence__gte", 0), ("vehicle_confidence__lte", 1)), _connector="OR"), name="cam_event_vehicle_conf_range")),
        migrations.AddConstraint(model_name="cameraevent", constraint=models.CheckConstraint(check=models.Q(("duration_seconds__isnull", True), ("duration_seconds__gte", 0), _connector="OR"), name="cam_event_duration_positive")),
        migrations.AddConstraint(model_name="cameraevent", constraint=models.CheckConstraint(check=models.Q(("vehicle_type__isnull", True), ("vehicle_type__in", ("car", "truck", "van", "bus", "motorcycle")), _connector="OR"), name="cam_event_vehicle_type_valid")),
        migrations.AddConstraint(model_name="cameraevent", constraint=models.CheckConstraint(check=models.Q(("direction__isnull", True), ("direction__in", ("entry", "exit")), _connector="OR"), name="cam_event_direction_valid")),
        migrations.AddConstraint(model_name="cameraevent", constraint=models.CheckConstraint(check=models.Q(("tamper_type__isnull", True), ("tamper_type__in", ("camera_covered", "camera_moved", "signal_lost", "out_of_focus")), _connector="OR"), name="cam_event_tamper_type_valid")),
    ]
