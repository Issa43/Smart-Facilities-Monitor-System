import uuid

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import BaseModel

from .registry import (
    ATTACHMENT_ENTITY_CHOICES,
    ATTACHMENT_ENTITY_TYPES,
    AttachmentEntityRegistry,
    AttachmentEntityRegistryError,
)
from .storage import get_protected_storage
from .validators import inspect_attachment_file, validate_attachment_file


class AttachmentFileType(models.TextChoices):
    PDF = "pdf", "PDF"
    JPEG = "jpeg", "JPEG"
    PNG = "png", "PNG"
    WEBP = "webp", "WebP"
    DOCX = "docx", "DOCX"
    XLSX = "xlsx", "XLSX"
    CSV = "csv", "CSV"
    TXT = "txt", "Plain text"


_FILE_EXTENSIONS = {
    AttachmentFileType.PDF: ".pdf",
    AttachmentFileType.JPEG: ".jpg",
    AttachmentFileType.PNG: ".png",
    AttachmentFileType.WEBP: ".webp",
    AttachmentFileType.DOCX: ".docx",
    AttachmentFileType.XLSX: ".xlsx",
    AttachmentFileType.CSV: ".csv",
    AttachmentFileType.TXT: ".txt",
}


def attachment_upload_path(instance, _filename):
    """Build a protected path without incorporating the client filename."""
    extension = _FILE_EXTENSIONS.get(instance.file_type, "")
    storage_name = f"{uuid.uuid4().hex}{extension}"
    return (
        f"attachments/{instance.entity_type}/"
        f"{instance.entity_id}/{storage_name}"
    )


class Attachment(BaseModel):
    entity_type = models.CharField(max_length=64, choices=ATTACHMENT_ENTITY_CHOICES)
    entity_id = models.UUIDField()
    file = models.FileField(
        upload_to=attachment_upload_path,
        storage=get_protected_storage,
        validators=[validate_attachment_file],
    )
    original_file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=10, choices=AttachmentFileType.choices)
    mime_type = models.CharField(max_length=127)
    file_size = models.PositiveBigIntegerField()

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["entity_type", "entity_id"],
                name="attach_entity_target_idx",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        try:
            AttachmentEntityRegistry.resolve(self.entity_type, self.entity_id)
        except AttachmentEntityRegistryError:
            errors["entity_id"] = "The active attachment target does not exist."

        if self.file and (self._state.adding or not self.file._committed):
            metadata = inspect_attachment_file(self.file)
            expected = {
                "original_file_name": metadata.original_file_name,
                "file_type": metadata.file_type,
                "mime_type": metadata.mime_type,
                "file_size": metadata.file_size,
            }
            for field_name, expected_value in expected.items():
                if getattr(self, field_name) != expected_value:
                    errors[field_name] = (
                        "File metadata must match the validated upload content."
                    )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.file and (self._state.adding or not self.file._committed):
            metadata = inspect_attachment_file(self.file)
            self.original_file_name = metadata.original_file_name
            self.file_type = metadata.file_type
            self.mime_type = metadata.mime_type
            self.file_size = metadata.file_size
        if not self._state.adding and self.pk:
            original = self.__class__.all_objects.get(pk=self.pk)
            immutable_fields = (
                "entity_type",
                "entity_id",
                "file",
                "original_file_name",
                "file_type",
                "mime_type",
                "file_size",
                "created_by_id",
                "created_at",
            )
            changed_fields = [
                field_name
                for field_name in immutable_fields
                if getattr(original, field_name) != getattr(self, field_name)
            ]
            if changed_fields:
                raise ValidationError(
                    "Attachment evidence is immutable: " + ", ".join(changed_fields)
                )
        else:
            self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Attachments cannot be hard-deleted; use soft deletion.")
        constraints = [
            models.CheckConstraint(
                check=models.Q(entity_type__in=ATTACHMENT_ENTITY_TYPES),
                name="attachment_entity_type_allowed",
            ),
            models.CheckConstraint(
                check=models.Q(file_size__gt=0),
                name="attachment_file_size_gt_zero",
            ),
        ]

    def __str__(self):
        return f"{self.original_file_name} ({self.entity_type}:{self.entity_id})"
