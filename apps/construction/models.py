import json
import uuid
from decimal import Decimal
from pathlib import PurePosixPath

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.common.models import BaseModel
from apps.attachments.storage import get_protected_storage
from apps.attachments.validators import inspect_attachment_file, validate_attachment_file


MAX_EQUIPMENT_ITEMS = 100
MAX_EQUIPMENT_ITEM_LENGTH = 100
MAX_EQUIPMENT_PAYLOAD_SIZE = 16 * 1024


def validate_equipment_used(value):
    if not isinstance(value, list):
        raise ValidationError("Equipment used must be a JSON array.")
    if len(value) > MAX_EQUIPMENT_ITEMS:
        raise ValidationError("Equipment used cannot contain more than 100 items.")

    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValidationError("Every equipment item must be a nonempty string.")
        if len(item) > MAX_EQUIPMENT_ITEM_LENGTH:
            raise ValidationError(
                "Equipment item names cannot exceed 100 characters."
            )

    encoded_payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
    if len(encoded_payload) > MAX_EQUIPMENT_PAYLOAD_SIZE:
        raise ValidationError("Equipment used exceeds the 16 KB payload limit.")


class DailyReport(BaseModel):
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        related_name="daily_reports",
    )
    phase = models.ForeignKey(
        "projects.ProjectPhase",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="daily_reports",
    )
    report_date = models.DateField()
    title = models.CharField(max_length=255, blank=True, default="")
    progress_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    weather_condition = models.CharField(max_length=100)
    workers_count = models.PositiveIntegerField(
        validators=[MinValueValidator(0)],
    )
    equipment_used = models.JSONField(
        default=list,
        blank=True,
        validators=[validate_equipment_used],
    )
    report_content = models.TextField()
    issues = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["project", "report_date"],
                name="daily_report_project_date_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "report_date", "created_by"],
                name="unique_daily_report_author_day",
            ),
            models.CheckConstraint(
                check=Q(workers_count__gte=0),
                name="daily_report_workers_nonnegative",
            ),
            models.CheckConstraint(
                check=Q(created_by__isnull=False),
                name="daily_report_creator_required",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.project_id and not self.project.is_active:
            errors["project"] = "Daily reports require an active project."

        if self.phase_id:
            if not self.phase.is_active:
                errors["phase"] = "Daily reports require an active phase."
            elif self.project_id and self.phase.project_id != self.project_id:
                errors["phase"] = "The selected phase must belong to the report project."

        if self._state.adding and not self.created_by_id:
            errors["created_by"] = "A daily report creator is required."

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.project} - {self.report_date}"


class QualityInspection(BaseModel):
    class Result(models.TextChoices):
        PASSED = "passed", "Passed"
        PASSED_WITH_NOTES = "passed_with_notes", "Passed with notes"
        FAILED = "failed", "Failed"

    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT, related_name="quality_inspections")
    phase = models.ForeignKey("projects.ProjectPhase", on_delete=models.PROTECT, related_name="quality_inspections")
    title = models.CharField(max_length=255)
    inspector = models.ForeignKey("users.User", on_delete=models.PROTECT, related_name="quality_inspections")
    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    result = models.CharField(max_length=20, choices=Result.choices)
    notes = models.TextField(blank=True, default="")
    inspected_at = models.DateTimeField()

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["project", "-inspected_at"], name="quality_project_time_idx"),
            models.Index(fields=["phase", "result"], name="quality_phase_result_idx"),
        ]
        constraints = [
            models.CheckConstraint(check=Q(score__gte=0, score__lte=100), name="quality_score_range"),
        ]

    def clean(self):
        super().clean()
        if self.phase_id and self.project_id and self.phase.project_id != self.project_id:
            raise ValidationError({"phase": "The phase must belong to the inspection project."})


def site_photo_upload_path(instance, filename):
    extension = PurePosixPath(str(filename or "").replace("\\", "/")).suffix.lower()
    return f"construction/site-photos/{instance.project_id}/{uuid.uuid4().hex}{extension}"


class SitePhoto(BaseModel):
    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT, related_name="site_photos")
    phase = models.ForeignKey("projects.ProjectPhase", null=True, blank=True, on_delete=models.PROTECT, related_name="site_photos")
    image = models.ImageField(upload_to=site_photo_upload_path, storage=get_protected_storage, validators=[validate_attachment_file])
    caption = models.CharField(max_length=500)
    captured_at = models.DateTimeField()
    original_file_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=127)
    file_size = models.PositiveBigIntegerField()

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["project", "-captured_at"], name="site_photo_project_time_idx"),
            models.Index(fields=["phase", "-captured_at"], name="site_photo_phase_time_idx"),
        ]
        constraints = [models.CheckConstraint(check=Q(file_size__gt=0), name="site_photo_size_positive")]

    def clean(self):
        super().clean()
        if self.phase_id and self.phase.project_id != self.project_id:
            raise ValidationError({"phase": "The phase must belong to the photo project."})
        if self.image and (self._state.adding or not self.image._committed):
            metadata = inspect_attachment_file(self.image)
            if metadata.file_type not in {"jpeg", "png", "webp"}:
                raise ValidationError({"image": "Site photos must be JPEG, PNG, or WebP."})

    def save(self, *args, **kwargs):
        if self.image and (self._state.adding or not self.image._committed):
            metadata = inspect_attachment_file(self.image)
            self.original_file_name = metadata.original_file_name
            self.mime_type = metadata.mime_type
            self.file_size = metadata.file_size
        self.full_clean()
        return super().save(*args, **kwargs)
