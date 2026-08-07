import json

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.common.models import BaseModel


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
    weather_condition = models.CharField(max_length=100)
    workers_count = models.PositiveIntegerField(
        validators=[MinValueValidator(0)],
    )
    equipment_used = models.JSONField(
        default=list,
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
