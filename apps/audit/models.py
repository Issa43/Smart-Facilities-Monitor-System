from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class AuditLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=100)
    entity_ref = models.CharField(max_length=255, blank=True, default="")
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")
    request_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["actor", "-created_at"], name="audit_actor_time_idx"),
            models.Index(fields=["entity_type", "entity_id", "-created_at"], name="audit_entity_time_idx"),
            models.Index(fields=["action", "-created_at"], name="audit_action_time_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Audit log entries are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit log entries cannot be deleted.")
