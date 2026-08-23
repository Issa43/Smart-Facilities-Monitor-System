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
