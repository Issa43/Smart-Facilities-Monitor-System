import django.db.models.deletion
import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0002_notification_deduplication_key"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DeviceRegistration",
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
                ("token", models.TextField()),
                (
                    "token_hash",
                    models.CharField(editable=False, max_length=64, unique=True),
                ),
                (
                    "platform",
                    models.CharField(
                        choices=[("android", "Android"), ("ios", "iOS")],
                        max_length=10,
                    ),
                ),
                ("last_seen_at", models.DateTimeField()),
                ("disabled_at", models.DateTimeField(blank=True, null=True)),
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
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="notification_devices",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["user", "is_active"],
                        name="notif_device_user_state_idx",
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        check=models.Q(("platform__in", ["android", "ios"])),
                        name="notif_device_platform_valid",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="PushDelivery",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("processing", "Processing"),
                            ("sent", "Sent"),
                            ("failed", "Failed"),
                            ("invalid_token", "Invalid token"),
                            ("skipped", "Skipped"),
                        ],
                        default="queued",
                        max_length=20,
                    ),
                ),
                ("attempt_count", models.PositiveSmallIntegerField(default=0)),
                ("failure_code", models.CharField(blank=True, default="", max_length=64)),
                (
                    "provider_message_id",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                ("processing_started_at", models.DateTimeField(blank=True, null=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
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
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="push_deliveries",
                        to="notifications.deviceregistration",
                    ),
                ),
                (
                    "notification",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="push_deliveries",
                        to="notifications.notification",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["status", "updated_at"],
                        name="push_delivery_state_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("notification", "device"),
                        name="unique_notification_device_push",
                    ),
                    models.CheckConstraint(
                        check=models.Q(
                            (
                                "status__in",
                                [
                                    "queued",
                                    "processing",
                                    "sent",
                                    "failed",
                                    "invalid_token",
                                    "skipped",
                                ],
                            )
                        ),
                        name="push_delivery_status_valid",
                    ),
                ],
            },
        ),
    ]
