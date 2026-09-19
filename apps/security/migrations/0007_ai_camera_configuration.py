import django.db.models.deletion
import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("security", "0006_cameraevent_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuthorizedVehicle",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("plate_number", models.CharField(max_length=32, unique=True)),
                ("responsible_name", models.CharField(max_length=255)),
                ("expires_on", models.DateField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"], "abstract": False},
        ),
        migrations.CreateModel(
            name="CameraAIModel",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("model_identifier", models.CharField(choices=[("fire_smoke", "Fire and smoke"), ("intrusion", "Intrusion"), ("anpr", "ANPR"), ("tamper", "Tamper")], max_length=20)),
                ("camera", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ai_models", to="security.camera")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"], "abstract": False},
        ),
        migrations.CreateModel(
            name="CameraROI",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("identifier", models.CharField(max_length=100)),
                ("name", models.CharField(max_length=150)),
                ("polygon", models.JSONField()),
                ("camera", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="rois", to="security.camera")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"], "abstract": False},
        ),
        migrations.CreateModel(
            name="RestrictedZoneSchedule",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("always_restricted", models.BooleanField(default=False)),
                ("from_time", models.TimeField(blank=True, null=True)),
                ("to_time", models.TimeField(blank=True, null=True)),
                ("days_of_week", models.JSONField(blank=True, default=list)),
                ("timezone_name", models.CharField(max_length=64)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("roi", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="restricted_schedule", to="security.cameraroi")),
            ],
            options={"ordering": ["-created_at"], "abstract": False},
        ),
        migrations.CreateModel(
            name="VirtualLine",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("line_start", models.JSONField()),
                ("line_end", models.JSONField()),
                ("camera", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="virtual_line", to="security.camera")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"], "abstract": False},
        ),
        migrations.AddField(
            model_name="cameraevent",
            name="roi",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="camera_events", to="security.cameraroi"),
        ),
        migrations.AddIndex(model_name="authorizedvehicle", index=models.Index(fields=["plate_number", "is_active"], name="auth_vehicle_plate_state_idx")),
        migrations.AddIndex(model_name="authorizedvehicle", index=models.Index(fields=["expires_on", "is_active"], name="auth_vehicle_expiry_state_idx")),
        migrations.AddConstraint(model_name="authorizedvehicle", constraint=models.CheckConstraint(check=~models.Q(plate_number=""), name="authorized_vehicle_plate_required")),
        migrations.AddConstraint(model_name="authorizedvehicle", constraint=models.CheckConstraint(check=~models.Q(responsible_name=""), name="authorized_vehicle_owner_required")),
        migrations.AddIndex(model_name="cameraaimodel", index=models.Index(fields=["camera", "is_active"], name="camera_ai_model_state_idx")),
        migrations.AddConstraint(model_name="cameraaimodel", constraint=models.UniqueConstraint(fields=("camera", "model_identifier"), name="unique_camera_ai_model")),
        migrations.AddConstraint(model_name="cameraaimodel", constraint=models.CheckConstraint(check=models.Q(model_identifier__in=("fire_smoke", "intrusion", "anpr", "tamper")), name="camera_ai_model_identifier_valid")),
        migrations.AddIndex(model_name="cameraroi", index=models.Index(fields=["camera", "is_active"], name="camera_roi_state_idx")),
        migrations.AddConstraint(model_name="cameraroi", constraint=models.UniqueConstraint(fields=("camera", "identifier"), name="unique_camera_roi_identifier")),
        migrations.AddConstraint(model_name="cameraroi", constraint=models.CheckConstraint(check=~models.Q(identifier=""), name="camera_roi_identifier_required")),
        migrations.AddConstraint(model_name="cameraroi", constraint=models.CheckConstraint(check=~models.Q(name=""), name="camera_roi_name_required")),
        migrations.AddIndex(model_name="restrictedzoneschedule", index=models.Index(fields=["is_active"], name="restricted_sched_state_idx")),
        migrations.AddConstraint(model_name="restrictedzoneschedule", constraint=models.CheckConstraint(check=(models.Q(always_restricted=True, from_time__isnull=True, to_time__isnull=True, days_of_week=[]) | models.Q(always_restricted=False, from_time__isnull=False, to_time__isnull=False)), name="restricted_schedule_mode_valid")),
        migrations.AddIndex(model_name="virtualline", index=models.Index(fields=["is_active"], name="virtual_line_state_idx")),
    ]
