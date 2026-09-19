import apps.security.models
import django.db.models.deletion
import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("security", "0004_incident_action_completion"),
    ]

    operations = [
        migrations.CreateModel(
            name="AIIngestionCredential",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("name", models.CharField(max_length=150)),
                (
                    "key_id",
                    models.CharField(
                        default=apps.security.models.generate_ai_credential_key_id,
                        editable=False,
                        max_length=40,
                        unique=True,
                    ),
                ),
                ("secret_hash", models.CharField(editable=False, max_length=255)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "principal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ai_ingestion_credentials",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "revoked_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="revoked_ai_ingestion_credentials",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["is_active", "expires_at"],
                        name="ai_credential_state_idx",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        check=(
                            models.Q(revoked_at__isnull=True, revoked_by__isnull=True)
                            | models.Q(
                                revoked_at__isnull=False,
                                revoked_by__isnull=False,
                            )
                        ),
                        name="ai_credential_revocation_fields_valid",
                    ),
                    models.CheckConstraint(
                        check=(
                            models.Q(revoked_at__isnull=True)
                            | models.Q(is_active=False)
                        ),
                        name="ai_credential_revoked_inactive",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="AIIngestionCameraScope",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "camera",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ai_ingestion_scopes",
                        to="security.camera",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "credential",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="camera_scopes",
                        to="security.aiingestioncredential",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["credential", "is_active"],
                        name="ai_scope_credential_idx",
                    ),
                    models.Index(
                        fields=["camera", "is_active"],
                        name="ai_scope_camera_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("credential", "camera"),
                        name="unique_ai_credential_camera_scope",
                    )
                ],
            },
        ),
    ]
