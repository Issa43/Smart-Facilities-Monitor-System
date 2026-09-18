import uuid
from decimal import Decimal
from pathlib import PurePosixPath

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.attachments.storage import get_protected_storage
from apps.attachments.validators import (
    PROJECT_IMAGE_MAX_FILE_SIZE,
    inspect_attachment_file,
    validate_attachment_file,
)
from apps.common.models import BaseModel
from apps.users.models import Role


PROJECT_FACILITY_TYPE_VALUES = (
    "commercial",
    "residential",
    "industrial",
    "healthcare",
    "education",
    "government",
    "mixed_use",
    "other",
)
PROJECT_STATUS_VALUES = (
    "planning",
    "in_progress",
    "completed",
    "operational",
)
PROJECT_ASSIGNMENT_ROLE_VALUES = (
    "primary_manager",
    "engineer",
    "supervisor",
    "viewer",
)
PROJECT_PHASE_PRIORITY_VALUES = ("low", "medium", "high", "critical")
PROJECT_PHASE_STATUS_VALUES = (
    "not_started",
    "in_progress",
    "completed",
    "rejected",
    "needs_modification",
)
PHASE_REVIEW_DECISION_VALUES = ("approved", "rejected")
PHASE_REVIEW_DISPOSITION_VALUES = ("needs_modification", "final_rejection")


def validate_project_image(uploaded_file):
    metadata = inspect_attachment_file(
        uploaded_file,
        max_size=PROJECT_IMAGE_MAX_FILE_SIZE,
    )
    if metadata.file_type not in {"jpeg", "png", "webp"}:
        raise ValidationError("Project images must be JPEG, PNG, or WebP.")


def project_image_upload_path(_instance, filename):
    normalized_name = str(filename or "").replace("\\", "/")
    extension = PurePosixPath(normalized_name).suffix.lower()
    if extension == ".jpeg":
        extension = ".jpg"
    return f"projects/images/{uuid.uuid4().hex}{extension}"


def project_document_upload_path(instance, filename):
    normalized_name = str(filename or "").replace("\\", "/")
    extension = PurePosixPath(normalized_name).suffix.lower()
    if extension == ".jpeg":
        extension = ".jpg"
    return f"projects/documents/{instance.project_id}/{uuid.uuid4().hex}{extension}"


class ImmutableHistoryMixin:
    """Prevent business-history mutation while retaining soft archival support."""

    immutable_fields = ()

    def save(self, *args, **kwargs):
        if not self._state.adding and self.pk:
            original = self.__class__.all_objects.get(pk=self.pk)
            changed_fields = [
                field_name
                for field_name in self.immutable_fields
                if getattr(original, field_name) != getattr(self, field_name)
            ]
            if changed_fields:
                raise ValidationError(
                    "Immutable history fields cannot be changed: "
                    + ", ".join(changed_fields)
                )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Historical records cannot be hard-deleted.")


class Project(BaseModel):
    class FacilityType(models.TextChoices):
        COMMERCIAL = "commercial", "Commercial"
        RESIDENTIAL = "residential", "Residential"
        INDUSTRIAL = "industrial", "Industrial"
        HEALTHCARE = "healthcare", "Healthcare"
        EDUCATION = "education", "Education"
        GOVERNMENT = "government", "Government"
        MIXED_USE = "mixed_use", "Mixed use"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PLANNING = "planning", "Planning"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        OPERATIONAL = "operational", "Operational"

    name = models.CharField(max_length=255)
    facility = models.ForeignKey(
        "facilities.Facility",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="projects",
    )
    facility_type = models.CharField(max_length=20, choices=FacilityType.choices)
    description = models.TextField(blank=True, default="")
    location = models.CharField(max_length=255)
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("-90")),
            MaxValueValidator(Decimal("90")),
        ],
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("-180")),
            MaxValueValidator(Decimal("180")),
        ],
    )
    image = models.ImageField(
        upload_to=project_image_upload_path,
        storage=get_protected_storage,
        validators=[validate_project_image],
        null=True,
        blank=True,
    )
    start_date = models.DateField()
    expected_completion_date = models.DateField()
    actual_completion_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNING,
    )

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["status"], name="project_status_idx"),
            models.Index(fields=["facility"], name="project_facility_idx"),
            models.Index(
                fields=["status", "expected_completion_date"],
                name="project_status_expected_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(expected_completion_date__gte=F("start_date")),
                name="project_expected_after_start",
            ),
            models.CheckConstraint(
                check=(
                    Q(actual_completion_date__isnull=True)
                    | Q(actual_completion_date__gte=F("start_date"))
                ),
                name="project_actual_after_start",
            ),
            models.CheckConstraint(
                check=(
                    Q(latitude__isnull=True)
                    | Q(latitude__gte=Decimal("-90"), latitude__lte=Decimal("90"))
                ),
                name="project_latitude_range",
            ),
            models.CheckConstraint(
                check=(
                    Q(longitude__isnull=True)
                    | Q(longitude__gte=Decimal("-180"), longitude__lte=Decimal("180"))
                ),
                name="project_longitude_range",
            ),
            models.CheckConstraint(
                check=Q(status__in=PROJECT_STATUS_VALUES),
                name="project_status_valid",
            ),
            models.CheckConstraint(
                check=Q(facility_type__in=PROJECT_FACILITY_TYPE_VALUES),
                name="project_facility_type_valid",
            ),
            models.CheckConstraint(
                check=(
                    ~Q(status__in=("completed", "operational"))
                    | Q(actual_completion_date__isnull=False)
                ),
                name="project_completed_has_actual",
            ),
            models.CheckConstraint(
                check=(~Q(status="operational") | Q(facility__isnull=False)),
                name="project_operational_has_facility",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if (
            self.start_date
            and self.expected_completion_date
            and self.expected_completion_date < self.start_date
        ):
            errors["expected_completion_date"] = (
                "Expected completion date cannot precede the start date."
            )

        if (
            self.start_date
            and self.actual_completion_date
            and self.actual_completion_date < self.start_date
        ):
            errors["actual_completion_date"] = (
                "Actual completion date cannot precede the start date."
            )

        if self.pk and self.start_date:
            phases_before_project_start = self.phases.filter(
                Q(start_date__lt=self.start_date)
                | Q(actual_start_date__lt=self.start_date)
            ).exists()
            if phases_before_project_start:
                errors["start_date"] = (
                    "Project start date cannot be later than an existing phase start date."
                )

        if (
            self.status in {self.Status.COMPLETED, self.Status.OPERATIONAL}
            and not self.actual_completion_date
        ):
            errors["actual_completion_date"] = (
                "A completed or operational project requires an actual completion date."
            )

        if self.status == self.Status.OPERATIONAL and not self.facility_id:
            errors["facility"] = "An operational project requires a facility."

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.name


class ProjectAssignment(BaseModel):
    class RoleType(models.TextChoices):
        PRIMARY_MANAGER = "primary_manager", "Primary manager"
        ENGINEER = "engineer", "Engineer"
        SUPERVISOR = "supervisor", "Supervisor"
        VIEWER = "viewer", "Viewer"

    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    user = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        related_name="project_assignments",
    )
    role_type = models.CharField(max_length=20, choices=RoleType.choices)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["user", "project"],
                name="project_assign_user_proj_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "user", "role_type"],
                name="unique_project_user_role_assignment",
            ),
            models.CheckConstraint(
                check=Q(role_type__in=PROJECT_ASSIGNMENT_ROLE_VALUES),
                name="project_assignment_role_valid",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.project_id and not self.project.is_active:
            errors["project"] = "Assignments require an active project."

        if self.user_id:
            if not self.user.is_active:
                errors["user"] = "Assignments require an active user."
            elif (
                not self.user.role_id
                or self.user.role.name != Role.CONSTRUCTION_MANAGER
            ):
                errors["user"] = (
                    "Only users with the Construction Manager role may be assigned."
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.user} - {self.project} ({self.get_role_type_display()})"


class ProjectPhase(BaseModel):
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not Started"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        REJECTED = "rejected", "Rejected"
        NEEDS_MODIFICATION = "needs_modification", "Needs Modification"

    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        related_name="phases",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    sequence_number = models.PositiveIntegerField()
    start_date = models.DateField()
    expected_completion_date = models.DateField()
    actual_start_date = models.DateField(null=True, blank=True)
    actual_completion_date = models.DateField(null=True, blank=True)
    initial_progress = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(Decimal("100")),
        ],
    )
    current_progress = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(Decimal("100")),
        ],
    )
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_STARTED,
    )
    approved_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["project", "sequence_number"],
                name="phase_project_sequence_idx",
            ),
            models.Index(
                fields=["project", "status"],
                name="phase_project_status_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "sequence_number"],
                name="unique_project_phase_sequence",
            ),
            models.CheckConstraint(
                check=Q(sequence_number__gt=0),
                name="phase_sequence_positive",
            ),
            models.CheckConstraint(
                check=Q(initial_progress__gte=0, initial_progress__lte=100),
                name="phase_initial_progress_range",
            ),
            models.CheckConstraint(
                check=Q(current_progress__gte=0, current_progress__lte=100),
                name="phase_current_progress_range",
            ),
            models.CheckConstraint(
                check=Q(current_progress__gte=F("initial_progress")),
                name="phase_current_gte_initial",
            ),
            models.CheckConstraint(
                check=Q(priority__in=PROJECT_PHASE_PRIORITY_VALUES),
                name="phase_priority_valid",
            ),
            models.CheckConstraint(
                check=Q(status__in=PROJECT_PHASE_STATUS_VALUES),
                name="phase_status_valid",
            ),
            models.CheckConstraint(
                check=Q(expected_completion_date__gte=F("start_date")),
                name="phase_expected_after_start",
            ),
            models.CheckConstraint(
                check=(
                    Q(actual_completion_date__isnull=True)
                    | (
                        Q(actual_start_date__isnull=False)
                        & Q(actual_completion_date__gte=F("actual_start_date"))
                    )
                ),
                name="phase_actual_dates_valid",
            ),
            models.CheckConstraint(
                check=(
                    (Q(approved_by__isnull=True) & Q(approved_at__isnull=True))
                    | (Q(approved_by__isnull=False) & Q(approved_at__isnull=False))
                ),
                name="phase_approval_fields_consistent",
            ),
            models.CheckConstraint(
                check=(
                    ~Q(status="completed")
                    | Q(current_progress=Decimal("100.00"))
                ),
                name="phase_completed_progress_full",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.project_id and not self.project.is_active:
            errors["project"] = "Phases require an active project."
        if (
            self.project_id
            and self.start_date
            and self.start_date < self.project.start_date
        ):
            errors["start_date"] = (
                "Phase start date cannot precede the project start date."
            )
        if (
            self.project_id
            and self.actual_start_date
            and self.actual_start_date < self.project.start_date
        ):
            errors["actual_start_date"] = (
                "Phase actual start date cannot precede the project start date."
            )
        if self.sequence_number is not None and self.sequence_number <= 0:
            errors["sequence_number"] = "Sequence number must be greater than zero."
        if (
            self.start_date
            and self.expected_completion_date
            and self.expected_completion_date < self.start_date
        ):
            errors["expected_completion_date"] = (
                "Expected completion date cannot precede the start date."
            )
        if self.actual_completion_date and not self.actual_start_date:
            errors["actual_start_date"] = (
                "Actual start date is required when actual completion is set."
            )
        elif (
            self.actual_start_date
            and self.actual_completion_date
            and self.actual_completion_date < self.actual_start_date
        ):
            errors["actual_completion_date"] = (
                "Actual completion date cannot precede the actual start date."
            )
        if (
            self.initial_progress is not None
            and self.current_progress is not None
            and self.current_progress < self.initial_progress
        ):
            errors["current_progress"] = (
                "Current progress cannot be below initial progress."
            )
        if not self._state.adding and self.pk and self.current_progress is not None:
            previous_progress = self.__class__.all_objects.only(
                "current_progress"
            ).get(pk=self.pk).current_progress
            if self.current_progress < previous_progress:
                errors["current_progress"] = "Phase progress cannot decrease."
        if (
            self.status == self.Status.COMPLETED
            and self.current_progress != Decimal("100.00")
        ):
            errors["current_progress"] = "Completed phases require 100% progress."
        if bool(self.approved_by_id) != bool(self.approved_at):
            errors["approved_at"] = (
                "Approved user and approval timestamp must be set together."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.project} - {self.sequence_number}: {self.name}"


class PhaseProgressLog(ImmutableHistoryMixin, BaseModel):
    immutable_fields = (
        "phase_id",
        "progress_percentage",
        "work_completed",
        "notes",
        "created_by_id",
        "created_at",
    )

    phase = models.ForeignKey(
        ProjectPhase,
        on_delete=models.PROTECT,
        related_name="progress_logs",
    )
    progress_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(Decimal("100")),
        ],
    )
    work_completed = models.TextField()
    notes = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["phase", "created_at"],
                name="phase_progress_created_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(progress_percentage__gte=0, progress_percentage__lte=100),
                name="phase_progress_log_range",
            ),
            models.CheckConstraint(
                check=Q(created_by__isnull=False),
                name="phase_progress_author_required",
            ),
        ]

    def clean(self):
        super().clean()
        if self.phase_id and (
            not self.phase.is_active or not self.phase.project.is_active
        ):
            raise ValidationError({"phase": "Progress requires an active phase and project."})
        if not self.created_by_id:
            raise ValidationError({"created_by": "A progress author is required."})

    def __str__(self):
        return f"{self.phase} - {self.progress_percentage}%"


class PhaseReviewLog(ImmutableHistoryMixin, BaseModel):
    class Decision(models.TextChoices):
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    class Disposition(models.TextChoices):
        NEEDS_MODIFICATION = "needs_modification", "Needs modification"
        FINAL_REJECTION = "final_rejection", "Final rejection"

    immutable_fields = (
        "phase_id",
        "decision",
        "disposition",
        "reason",
        "created_by_id",
        "created_at",
    )

    phase = models.ForeignKey(
        ProjectPhase,
        on_delete=models.PROTECT,
        related_name="review_logs",
    )
    decision = models.CharField(max_length=10, choices=Decision.choices)
    disposition = models.CharField(
        max_length=20,
        choices=Disposition.choices,
        null=True,
        blank=True,
    )
    reason = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        constraints = [
            models.CheckConstraint(
                check=Q(decision__in=PHASE_REVIEW_DECISION_VALUES),
                name="phase_review_decision_valid",
            ),
            models.CheckConstraint(
                check=(
                    Q(disposition__isnull=True)
                    | Q(disposition__in=PHASE_REVIEW_DISPOSITION_VALUES)
                ),
                name="phase_review_disposition_valid",
            ),
            models.CheckConstraint(
                check=(
                    (
                        Q(decision="approved")
                        & Q(disposition__isnull=True)
                    )
                    | (
                        Q(decision="rejected")
                        & Q(disposition__isnull=False)
                        & ~Q(reason="")
                    )
                ),
                name="phase_review_payload_valid",
            ),
            models.CheckConstraint(
                check=Q(created_by__isnull=False),
                name="phase_review_reviewer_required",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.phase_id and (
            not self.phase.is_active or not self.phase.project.is_active
        ):
            errors["phase"] = "Reviews require an active phase and project."
        if not self.created_by_id:
            errors["created_by"] = "A phase reviewer is required."
        if self.decision == self.Decision.APPROVED and self.disposition is not None:
            errors["disposition"] = "Approved reviews cannot have a rejection disposition."
        if self.decision == self.Decision.REJECTED:
            if not self.disposition:
                errors["disposition"] = "Rejected reviews require a disposition."
            if not (self.reason or "").strip():
                errors["reason"] = "Rejected reviews require a reason."

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.phase} - {self.get_decision_display()}"


class ProjectDocument(ImmutableHistoryMixin, BaseModel):
    immutable_fields = (
        "project_id",
        "document_type",
        "title",
        "file",
        "original_file_name",
        "mime_type",
        "file_size",
        "created_by_id",
        "created_at",
    )

    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        related_name="documents",
    )
    document_type = models.CharField(max_length=50)
    title = models.CharField(max_length=255)
    file = models.FileField(
        upload_to=project_document_upload_path,
        storage=get_protected_storage,
        validators=[validate_attachment_file],
    )
    original_file_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=127)
    file_size = models.PositiveBigIntegerField()

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["project", "created_at"],
                name="project_document_created_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(file_size__gt=0),
                name="project_document_size_positive",
            ),
            models.CheckConstraint(
                check=Q(created_by__isnull=False),
                name="project_document_uploader_req",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.project_id and not self.project.is_active:
            errors["project"] = "Documents require an active project."
        if not self.created_by_id:
            errors["created_by"] = "A document uploader is required."

        if self._state.adding and self.file:
            metadata = inspect_attachment_file(self.file)
            if self.original_file_name != metadata.original_file_name:
                errors["original_file_name"] = (
                    "Original file name must match the validated upload metadata."
                )
            if self.mime_type != metadata.mime_type:
                errors["mime_type"] = (
                    "MIME type must match the validated upload content."
                )
            if self.file_size != metadata.file_size:
                errors["file_size"] = (
                    "File size must match the validated upload content."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.file and (self._state.adding or not self.file._committed):
            metadata = inspect_attachment_file(self.file)
            self.original_file_name = metadata.original_file_name
            self.mime_type = metadata.mime_type
            self.file_size = metadata.file_size
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.project} - {self.title}"
