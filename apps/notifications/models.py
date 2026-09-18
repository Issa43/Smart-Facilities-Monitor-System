import hashlib

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.models import BaseModel


class Notification(BaseModel):
    class Category(models.TextChoices):
        PROJECT = "project", "Project"
        MATERIAL = "material", "Material"
        MAINTENANCE = "maintenance", "Maintenance"
        SECURITY = "security", "Security"
        SAFETY = "safety", "Safety"
        SYSTEM = "system", "System"

    class Tone(models.TextChoices):
        NEUTRAL = "neutral", "Neutral"
        INFO = "info", "Info"
        SUCCESS = "success", "Success"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="notifications",
    )
    title = models.CharField(max_length=255)
    body = models.TextField()
    category = models.CharField(max_length=20, choices=Category.choices)
    tone = models.CharField(max_length=10, choices=Tone.choices, default=Tone.INFO)
    href = models.CharField(max_length=500, null=True, blank=True)
    source_type = models.CharField(max_length=64, null=True, blank=True)
    source_id = models.UUIDField(null=True, blank=True)
    deduplication_key = models.CharField(max_length=255, unique=True, null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["recipient", "read_at", "-created_at"], name="notif_recipient_read_idx"),
            models.Index(fields=["source_type", "source_id"], name="notif_source_idx"),
        ]
        constraints = [
            models.CheckConstraint(check=~Q(title=""), name="notification_title_required"),
            models.CheckConstraint(check=~Q(body=""), name="notification_body_required"),
        ]

    @property
    def is_read(self):
        return self.read_at is not None


class NotificationPreference(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
    )
    low_stock = models.BooleanField(default=True)
    overdue_work_orders = models.BooleanField(default=True)
    critical_alerts = models.BooleanField(default=True)
    stage_review = models.BooleanField(default=True)


class DeviceRegistration(BaseModel):
    class Platform(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="notification_devices",
    )
    # The registration token must remain recoverable for FCM transport. It is
    # write-only at the API boundary and must never be included in logs.
    token = models.TextField()
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    platform = models.CharField(max_length=10, choices=Platform.choices)
    last_seen_at = models.DateTimeField()
    disabled_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["user", "is_active"],
                name="notif_device_user_state_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(platform__in=["android", "ios"]),
                name="notif_device_platform_valid",
            ),
        ]

    @staticmethod
    def hash_token(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def save(self, *args, **kwargs):
        self.token_hash = self.hash_token(self.token)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user_id}:{self.platform}:{self.pk}"


class PushDelivery(BaseModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        INVALID_TOKEN = "invalid_token", "Invalid token"
        SKIPPED = "skipped", "Skipped"

    notification = models.ForeignKey(
        Notification,
        on_delete=models.PROTECT,
        related_name="push_deliveries",
    )
    device = models.ForeignKey(
        DeviceRegistration,
        on_delete=models.PROTECT,
        related_name="push_deliveries",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    failure_code = models.CharField(max_length=64, blank=True, default="")
    provider_message_id = models.CharField(max_length=255, blank=True, default="")
    processing_started_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["status", "updated_at"], name="push_delivery_state_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["notification", "device"],
                name="unique_notification_device_push",
            ),
            models.CheckConstraint(
                check=Q(
                    status__in=[
                        "queued",
                        "processing",
                        "sent",
                        "failed",
                        "invalid_token",
                        "skipped",
                    ]
                ),
                name="push_delivery_status_valid",
            ),
        ]
