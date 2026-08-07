import uuid
from pathlib import PurePosixPath

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.attachments.storage import get_protected_storage
from apps.attachments.validators import inspect_attachment_file
from apps.common.models import BaseModel


REPORT_MODULE_VALUES = (
    "construction",
    "materials",
    "assets",
    "maintenance",
    "security",
)
REPORT_FORMAT_VALUES = ("pdf", "excel")
REPORT_STATUS_VALUES = ("queued", "processing", "completed", "failed")


def validate_report_file(uploaded_file):
    metadata = inspect_attachment_file(uploaded_file)
    if metadata.file_type not in {"pdf", "xlsx"}:
        raise ValidationError("Generated reports must be PDF or XLSX files.")


def report_upload_path(instance, filename):
    normalized_name = str(filename or "").replace("\\", "/")
    extension = PurePosixPath(normalized_name).suffix.lower()
    return f"reports/{instance.module}/{uuid.uuid4().hex}{extension}"


class ReportTemplate(BaseModel):
    class Module(models.TextChoices):
        CONSTRUCTION = "construction", "Construction"
        MATERIALS = "materials", "Materials"
        ASSETS = "assets", "Assets"
        MAINTENANCE = "maintenance", "Maintenance"
        SECURITY = "security", "Security"

    class Format(models.TextChoices):
        PDF = "pdf", "PDF"
        EXCEL = "excel", "Excel"

    name = models.CharField(max_length=255)
    module = models.CharField(max_length=20, choices=Module.choices)
    format = models.CharField(max_length=10, choices=Format.choices)
    configuration = models.JSONField(default=dict)

    class Meta(BaseModel.Meta):
        constraints = [
            models.CheckConstraint(
                check=Q(module__in=REPORT_MODULE_VALUES),
                name="report_template_module_valid",
            ),
            models.CheckConstraint(
                check=Q(format__in=REPORT_FORMAT_VALUES),
                name="report_template_format_valid",
            ),
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.configuration, dict):
            raise ValidationError(
                {"configuration": "Report template configuration must be an object."}
            )

    def __str__(self):
        return self.name


class Report(BaseModel):
    class Module(models.TextChoices):
        CONSTRUCTION = "construction", "Construction"
        MATERIALS = "materials", "Materials"
        ASSETS = "assets", "Assets"
        MAINTENANCE = "maintenance", "Maintenance"
        SECURITY = "security", "Security"

    class Format(models.TextChoices):
        PDF = "pdf", "PDF"
        EXCEL = "excel", "Excel"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    type = models.CharField(max_length=100)
    module = models.CharField(max_length=20, choices=Module.choices)
    parameters = models.JSONField(default=dict)
    file_path = models.FileField(
        upload_to=report_upload_path,
        storage=get_protected_storage,
        validators=[validate_report_file],
        max_length=500,
        null=True,
        blank=True,
    )
    format = models.CharField(max_length=10, choices=Format.choices)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.QUEUED,
    )

    class Meta(BaseModel.Meta):
        constraints = [
            models.CheckConstraint(
                check=Q(module__in=REPORT_MODULE_VALUES),
                name="report_module_valid",
            ),
            models.CheckConstraint(
                check=Q(format__in=REPORT_FORMAT_VALUES),
                name="report_format_valid",
            ),
            models.CheckConstraint(
                check=Q(status__in=REPORT_STATUS_VALUES),
                name="report_status_valid",
            ),
            models.CheckConstraint(
                check=Q(created_by__isnull=False),
                name="report_creator_required",
            ),
            models.CheckConstraint(
                check=(~Q(status="completed") | Q(file_path__isnull=False)),
                name="report_completed_has_file",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if not self.created_by_id:
            errors["created_by"] = "A report creator is required."
        if not isinstance(self.parameters, dict):
            errors["parameters"] = "Report parameters must be an object."
        if self.status == self.Status.COMPLETED and not self.file_path:
            errors["file_path"] = "Completed reports require a generated file."

        if self.file_path:
            metadata = inspect_attachment_file(self.file_path)
            expected_file_type = "pdf" if self.format == self.Format.PDF else "xlsx"
            if metadata.file_type != expected_file_type:
                errors["file_path"] = "The generated file must match the report format."

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.type} ({self.get_format_display()})"
