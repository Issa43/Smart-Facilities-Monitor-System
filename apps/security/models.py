import uuid
from decimal import Decimal
from pathlib import PurePosixPath

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.attachments.storage import get_protected_storage
from apps.attachments.validators import inspect_attachment_file
from apps.common.models import BaseModel


ALERT_TYPE_VALUES = ("fire", "smoke", "intrusion", "motion", "vehicle")
SECURITY_SEVERITY_VALUES = ("low", "medium", "high", "critical")
ALERT_SOURCE_VALUES = ("ai_detection", "manual", "sensor")
ALERT_STATUS_VALUES = ("new", "reviewed", "converted", "dismissed")
INCIDENT_STATUS_VALUES = ("open", "investigation", "transferred", "closed")


def validate_security_snapshot(uploaded_file):
    metadata = inspect_attachment_file(uploaded_file)
    if metadata.file_type not in {"jpeg", "png", "webp"}:
        raise ValidationError("Security snapshots must be JPEG, PNG, or WebP.")


def security_snapshot_upload_path(instance, filename):
    normalized_name = str(filename or "").replace("\\", "/")
    extension = PurePosixPath(normalized_name).suffix.lower()
    if extension == ".jpeg":
        extension = ".jpg"
    return f"security/alerts/{instance.facility_id}/{uuid.uuid4().hex}{extension}"


def generate_incident_number():
    return f"INC-{uuid.uuid4().hex[:16].upper()}"


class SecurityAlert(BaseModel):
    class AlertType(models.TextChoices):
        FIRE = "fire", "Fire"
        SMOKE = "smoke", "Smoke"
        INTRUSION = "intrusion", "Intrusion"
        MOTION = "motion", "Motion"
        VEHICLE = "vehicle", "Vehicle"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Source(models.TextChoices):
        AI_DETECTION = "ai_detection", "AI detection"
        MANUAL = "manual", "Manual"
        SENSOR = "sensor", "Sensor"

    class Status(models.TextChoices):
        NEW = "new", "New"
        REVIEWED = "reviewed", "Reviewed"
        CONVERTED = "converted", "Converted"
        DISMISSED = "dismissed", "Dismissed"

    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.PROTECT,
        related_name="security_alerts",
    )
    alert_type = models.CharField(max_length=20, choices=AlertType.choices)
    location = models.CharField(max_length=255)
    severity_level = models.CharField(max_length=10, choices=Severity.choices)
    source = models.CharField(max_length=20, choices=Source.choices)
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(Decimal("1")),
        ],
    )
    snapshot_image = models.ImageField(
        upload_to=security_snapshot_upload_path,
        storage=get_protected_storage,
        validators=[validate_security_snapshot],
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.NEW,
    )
    is_false_positive = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_security_alerts",
    )
    review_notes = models.TextField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["facility", "status"],
                name="security_alert_fac_status_idx",
            ),
            models.Index(
                fields=["-created_at"],
                name="security_alert_created_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(alert_type__in=ALERT_TYPE_VALUES),
                name="security_alert_type_valid",
            ),
            models.CheckConstraint(
                check=Q(severity_level__in=SECURITY_SEVERITY_VALUES),
                name="security_alert_severity_valid",
            ),
            models.CheckConstraint(
                check=Q(source__in=ALERT_SOURCE_VALUES),
                name="security_alert_source_valid",
            ),
            models.CheckConstraint(
                check=Q(status__in=ALERT_STATUS_VALUES),
                name="security_alert_status_valid",
            ),
            models.CheckConstraint(
                check=(
                    Q(confidence_score__isnull=True)
                    | Q(confidence_score__gte=0, confidence_score__lte=1)
                ),
                name="security_alert_confidence_range",
            ),
            models.CheckConstraint(
                check=(
                    Q(source="ai_detection")
                    | Q(confidence_score__isnull=True)
                ),
                name="security_alert_confidence_ai_only",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.facility_id and not self.facility.is_active:
            errors["facility"] = "Security alerts require an active facility."
        if self.source != self.Source.AI_DETECTION and self.confidence_score is not None:
            errors["confidence_score"] = (
                "Confidence score is only valid for AI detection alerts."
            )
        if self.is_false_positive and not self.reviewed_by_id:
            errors["reviewed_by"] = "False-positive alerts require a reviewer."

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.get_alert_type_display()} alert at {self.facility}"


class Incident(BaseModel):
    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        INVESTIGATION = "investigation", "Investigation"
        TRANSFERRED = "transferred", "Transferred"
        CLOSED = "closed", "Closed"

    incident_number = models.CharField(
        max_length=20,
        unique=True,
        default=generate_incident_number,
        editable=False,
    )
    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.PROTECT,
        related_name="incidents",
    )
    alert = models.OneToOneField(
        SecurityAlert,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="incident",
    )
    incident_type = models.CharField(max_length=100)
    description = models.TextField()
    location = models.CharField(max_length=255)
    severity_level = models.CharField(max_length=10, choices=Severity.choices)
    assigned_to = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_security_incidents",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    final_report = models.TextField(null=True, blank=True)
    closed_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="closed_security_incidents",
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["facility", "status"],
                name="incident_facility_status_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(severity_level__in=SECURITY_SEVERITY_VALUES),
                name="incident_severity_valid",
            ),
            models.CheckConstraint(
                check=Q(status__in=INCIDENT_STATUS_VALUES),
                name="incident_status_valid",
            ),
            models.CheckConstraint(
                check=Q(created_by__isnull=False),
                name="incident_creator_required",
            ),
            models.CheckConstraint(
                check=(
                    (
                        Q(status="closed")
                        & Q(closed_by__isnull=False)
                        & Q(closed_at__isnull=False)
                    )
                    | (
                        ~Q(status="closed")
                        & Q(closed_by__isnull=True)
                        & Q(closed_at__isnull=True)
                    )
                ),
                name="incident_closure_fields_valid",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.facility_id and not self.facility.is_active:
            errors["facility"] = "Incidents require an active facility."
        if self.alert_id:
            if not self.alert.is_active:
                errors["alert"] = "Incidents require an active alert."
            elif self.facility_id and self.alert.facility_id != self.facility_id:
                errors["alert"] = "The alert must belong to the incident facility."
        if not self.created_by_id:
            errors["created_by"] = "An incident creator is required."

        closure_fields_set = bool(self.closed_by_id) and bool(self.closed_at)
        if self.status == self.Status.CLOSED and not closure_fields_set:
            errors["closed_at"] = (
                "Closed incidents require both a closing user and timestamp."
            )
        elif self.status != self.Status.CLOSED and (self.closed_by_id or self.closed_at):
            errors["closed_at"] = (
                "Closure fields are only valid when the incident is closed."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.incident_number


class IncidentAction(BaseModel):
    incident = models.ForeignKey(
        Incident,
        on_delete=models.PROTECT,
        related_name="actions",
    )
    action_taken = models.TextField()
    notes = models.TextField(blank=True, default="")
    taken_by = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        related_name="security_incident_actions",
    )
    taken_at = models.DateTimeField(default=timezone.now)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["incident", "taken_at"],
                name="incident_action_time_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=~Q(action_taken=""),
                name="incident_action_required",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.incident_id and (
            not self.incident.is_active or not self.incident.facility.is_active
        ):
            errors["incident"] = (
                "Incident actions require an active incident and facility."
            )
        if not self.taken_by_id:
            errors["taken_by"] = "An incident action actor is required."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self._state.adding and self.pk:
            original = self.__class__.all_objects.get(pk=self.pk)
            immutable_fields = (
                "incident_id",
                "action_taken",
                "notes",
                "taken_by_id",
                "taken_at",
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
                    "Incident action history is immutable: "
                    + ", ".join(changed_fields)
                )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Incident actions cannot be hard-deleted.")

    def __str__(self):
        return f"{self.incident} - {self.taken_at.isoformat()}"
