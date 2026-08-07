import uuid

from django.conf import settings
from django.db import models


class ActiveManager(models.Manager):
    """Default manager: only returns rows where is_active=True (soft-delete aware)."""

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class BaseModel(models.Model):
    """
    Abstract base class for (almost) every domain model in SFLMS.

    Decisions locked in the approved architecture document:
    - UUID primary keys (unguessable IDs, important for the Security module).
    - Soft delete via `is_active` instead of physical deletion.
    - `created_by` / `created_at` / `updated_at` audit trail on every row,
      complementary to (not a replacement for) the dedicated `audit` app.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    is_active = models.BooleanField(default=True)

    objects = ActiveManager()
    all_objects = models.Manager()  # includes soft-deleted rows

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def soft_delete(self):
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])
