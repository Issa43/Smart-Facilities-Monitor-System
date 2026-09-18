import math
import uuid
from decimal import Decimal
from pathlib import PurePosixPath
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.attachments.storage import get_protected_storage
from apps.attachments.validators import inspect_attachment_file, validate_attachment_file
from apps.common.models import BaseModel


ALERT_TYPE_VALUES = (
    "fire",
    "smoke",
    "intrusion",
    "motion",
    "unauthorized_person",
    "emergency",
    "vehicle",
    "tamper",
)
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


def generate_ai_credential_key_id():
    """Return a public, non-secret identifier for a machine credential."""
    return f"aic_{uuid.uuid4().hex}"


class SecurityAlert(BaseModel):
    class AlertType(models.TextChoices):
        FIRE = "fire", "Fire"
        SMOKE = "smoke", "Smoke"
        INTRUSION = "intrusion", "Intrusion"
        MOTION = "motion", "Motion"
        UNAUTHORIZED_PERSON = "unauthorized_person", "Unauthorized Person"
        EMERGENCY = "emergency", "Emergency"
        VEHICLE = "vehicle", "Vehicle"
        TAMPER = "tamper", "Tamper"

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
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="completed_incident_actions",
    )

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
            models.CheckConstraint(
                check=(
                    (Q(completed_at__isnull=True) & Q(completed_by__isnull=True))
                    | (Q(completed_at__isnull=False) & Q(completed_by__isnull=False))
                ),
                name="incident_action_completion_fields_valid",
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


class IncidentNote(BaseModel):
    incident = models.ForeignKey(Incident, on_delete=models.PROTECT, related_name="notes")
    body = models.TextField()
    author = models.ForeignKey("users.User", on_delete=models.PROTECT, related_name="security_incident_notes")

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=["incident", "-created_at"], name="incident_note_time_idx")]
        constraints = [models.CheckConstraint(check=~Q(body=""), name="incident_note_body_required")]

    def save(self, *args, **kwargs):
        if not self._state.adding and self.pk:
            original = self.__class__.all_objects.get(pk=self.pk)
            if original.body != self.body or original.author_id != self.author_id:
                raise ValidationError("Incident notes are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Incident notes cannot be hard-deleted.")


class Camera(BaseModel):
    class Status(models.TextChoices):
        ONLINE = "online", "Online"
        OFFLINE = "offline", "Offline"
        DEGRADED = "degraded", "Degraded"
        MAINTENANCE = "maintenance", "Maintenance"

    facility = models.ForeignKey("facilities.Facility", on_delete=models.PROTECT, related_name="cameras")
    asset = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.PROTECT, related_name="cameras")
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    zone = models.CharField(max_length=255)
    stream_reference = models.CharField(max_length=500, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OFFLINE)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["facility", "status"], name="camera_facility_status_idx"),
            models.Index(fields=["-last_seen_at"], name="camera_last_seen_idx"),
        ]

    def clean(self):
        super().clean()
        if self.asset_id and self.asset.facility_id != self.facility_id:
            raise ValidationError({"asset": "The camera asset must belong to the camera facility."})


def _validate_pixel_point(point, field_name):
    if not isinstance(point, dict) or set(point) != {"x", "y"}:
        raise ValidationError(
            {field_name: "Each point must contain exactly numeric x and y values."}
        )
    for coordinate in (point["x"], point["y"]):
        if (
            isinstance(coordinate, bool)
            or not isinstance(coordinate, (int, float))
            or not math.isfinite(coordinate)
            or coordinate < 0
        ):
            raise ValidationError(
                {field_name: "Pixel coordinates must be finite non-negative numbers."}
            )


def validate_roi_polygon(polygon):
    if not isinstance(polygon, list) or len(polygon) < 3:
        raise ValidationError(
            {"polygon": "An ROI polygon requires at least three ordered points."}
        )
    for point in polygon:
        _validate_pixel_point(point, "polygon")
    vertices = [(point["x"], point["y"]) for point in polygon]
    if len(set(vertices)) < 3:
        raise ValidationError({"polygon": "An ROI polygon requires three distinct points."})
    area_twice = sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(vertices, vertices[1:] + vertices[:1])
    )
    if area_twice == 0:
        raise ValidationError({"polygon": "An ROI polygon must enclose a non-zero area."})


def validate_virtual_line_points(line_start, line_end):
    _validate_pixel_point(line_start, "line_start")
    _validate_pixel_point(line_end, "line_end")
    if line_start == line_end:
        raise ValidationError(
            {"line_end": "Virtual-line endpoints must not be identical."}
        )


class CameraROI(BaseModel):
    camera = models.ForeignKey(
        Camera,
        on_delete=models.PROTECT,
        related_name="rois",
    )
    identifier = models.CharField(max_length=100)
    name = models.CharField(max_length=150)
    polygon = models.JSONField()

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["camera", "is_active"], name="camera_roi_state_idx")
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["camera", "identifier"],
                name="unique_camera_roi_identifier",
            ),
            models.CheckConstraint(
                check=~Q(identifier=""),
                name="camera_roi_identifier_required",
            ),
            models.CheckConstraint(check=~Q(name=""), name="camera_roi_name_required"),
        ]

    def clean(self):
        super().clean()
        errors = {}
        self.identifier = (self.identifier or "").strip()
        self.name = (self.name or "").strip()
        if not self.identifier:
            errors["identifier"] = "An ROI identifier is required."
        if not self.name:
            errors["name"] = "An ROI name is required."
        if self.camera_id and self.is_active and (
            not self.camera.is_active or not self.camera.facility.is_active
        ):
            errors["camera"] = "Active ROIs require an active camera and facility."
        try:
            validate_roi_polygon(self.polygon)
        except ValidationError as exc:
            errors.update(exc.message_dict)
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.camera.code}:{self.identifier}"


class RestrictedZoneSchedule(BaseModel):
    roi = models.OneToOneField(
        CameraROI,
        on_delete=models.PROTECT,
        related_name="restricted_schedule",
    )
    always_restricted = models.BooleanField(default=False)
    from_time = models.TimeField(null=True, blank=True)
    to_time = models.TimeField(null=True, blank=True)
    days_of_week = models.JSONField(default=list, blank=True)
    timezone_name = models.CharField(max_length=64)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["is_active"], name="restricted_sched_state_idx")
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(
                        always_restricted=True,
                        from_time__isnull=True,
                        to_time__isnull=True,
                        days_of_week=[],
                    )
                    | Q(
                        always_restricted=False,
                        from_time__isnull=False,
                        to_time__isnull=False,
                    )
                ),
                name="restricted_schedule_mode_valid",
            )
        ]

    def clean(self):
        super().clean()
        errors = {}
        try:
            ZoneInfo(self.timezone_name)
        except (TypeError, ValueError, ZoneInfoNotFoundError):
            errors["timezone_name"] = "Use a valid IANA timezone identifier."
        if not isinstance(self.days_of_week, list) or any(
            isinstance(day, bool) or not isinstance(day, int) or day not in range(7)
            for day in self.days_of_week
        ):
            errors["days_of_week"] = "days_of_week must be a list of integers from 0 to 6."
        elif len(set(self.days_of_week)) != len(self.days_of_week):
            errors["days_of_week"] = "days_of_week must not contain duplicates."
        if self.always_restricted:
            if self.from_time is not None or self.to_time is not None or self.days_of_week:
                errors["always_restricted"] = (
                    "Always-restricted schedules must not define times or days."
                )
        else:
            if self.from_time is None or self.to_time is None or not self.days_of_week:
                errors["from_time"] = (
                    "Scheduled restrictions require from_time, to_time, and days_of_week."
                )
            elif self.from_time == self.to_time:
                errors["to_time"] = "Scheduled restriction times must differ."
        if self.roi_id and self.is_active and (
            not self.roi.is_active
            or not self.roi.camera.is_active
            or not self.roi.camera.facility.is_active
        ):
            errors["roi"] = "Active schedules require an active ROI, camera, and facility."
        if errors:
            raise ValidationError(errors)

    @property
    def crosses_midnight(self):
        return bool(
            not self.always_restricted
            and self.from_time is not None
            and self.to_time is not None
            and self.from_time > self.to_time
        )

    def __str__(self):
        return f"Restricted schedule for {self.roi}"


class VirtualLine(BaseModel):
    camera = models.OneToOneField(
        Camera,
        on_delete=models.PROTECT,
        related_name="virtual_line",
    )
    line_start = models.JSONField()
    line_end = models.JSONField()

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["is_active"], name="virtual_line_state_idx")
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.camera_id and self.is_active and (
            not self.camera.is_active or not self.camera.facility.is_active
        ):
            errors["camera"] = "Active virtual lines require an active camera and facility."
        try:
            validate_virtual_line_points(self.line_start, self.line_end)
        except ValidationError as exc:
            errors.update(exc.message_dict)
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Virtual line for {self.camera.code}"


class AuthorizedVehicle(BaseModel):
    plate_number = models.CharField(max_length=32, unique=True)
    responsible_name = models.CharField(max_length=255)
    expires_on = models.DateField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["plate_number", "is_active"], name="auth_vehicle_plate_state_idx"),
            models.Index(fields=["expires_on", "is_active"], name="auth_vehicle_expiry_state_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=~Q(plate_number=""),
                name="authorized_vehicle_plate_required",
            ),
            models.CheckConstraint(
                check=~Q(responsible_name=""),
                name="authorized_vehicle_owner_required",
            ),
        ]

    @staticmethod
    def normalize_plate(value):
        return (value or "").strip().upper()

    def clean(self):
        super().clean()
        self.plate_number = self.normalize_plate(self.plate_number)
        self.responsible_name = (self.responsible_name or "").strip()
        errors = {}
        if not self.plate_number:
            errors["plate_number"] = "A plate number is required."
        if not self.responsible_name:
            errors["responsible_name"] = "A responsible name is required."
        if errors:
            raise ValidationError(errors)

    @property
    def is_currently_authorized(self):
        return bool(
            self.is_active
            and (self.expires_on is None or self.expires_on >= timezone.localdate())
        )

    def __str__(self):
        return self.plate_number


CAMERA_AI_MODEL_VALUES = ("fire_smoke", "intrusion", "anpr", "tamper")


class CameraAIModel(BaseModel):
    class ModelIdentifier(models.TextChoices):
        FIRE_SMOKE = "fire_smoke", "Fire and smoke"
        INTRUSION = "intrusion", "Intrusion"
        ANPR = "anpr", "ANPR"
        TAMPER = "tamper", "Tamper"

    camera = models.ForeignKey(
        Camera,
        on_delete=models.PROTECT,
        related_name="ai_models",
    )
    model_identifier = models.CharField(
        max_length=20,
        choices=ModelIdentifier.choices,
    )

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["camera", "is_active"], name="camera_ai_model_state_idx")
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["camera", "model_identifier"],
                name="unique_camera_ai_model",
            ),
            models.CheckConstraint(
                check=Q(model_identifier__in=CAMERA_AI_MODEL_VALUES),
                name="camera_ai_model_identifier_valid",
            ),
        ]

    def clean(self):
        super().clean()
        if self.camera_id and self.is_active and (
            not self.camera.is_active or not self.camera.facility.is_active
        ):
            raise ValidationError(
                {"camera": "Active AI models require an active camera and facility."}
            )

    def __str__(self):
        return f"{self.camera.code}:{self.model_identifier}"


class AIIngestionCredential(BaseModel):
    """Revocable machine credential for a roleless, non-interactive principal."""

    name = models.CharField(max_length=150)
    principal = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        related_name="ai_ingestion_credentials",
    )
    key_id = models.CharField(
        max_length=40,
        unique=True,
        default=generate_ai_credential_key_id,
        editable=False,
    )
    secret_hash = models.CharField(max_length=255, editable=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="revoked_ai_ingestion_credentials",
    )

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["is_active", "expires_at"],
                name="ai_credential_state_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(revoked_at__isnull=True, revoked_by__isnull=True)
                    | Q(revoked_at__isnull=False, revoked_by__isnull=False)
                ),
                name="ai_credential_revocation_fields_valid",
            ),
            models.CheckConstraint(
                check=Q(revoked_at__isnull=True) | Q(is_active=False),
                name="ai_credential_revoked_inactive",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.principal_id:
            if self.principal.role_id:
                errors["principal"] = "Machine principals must not have a human role."
            if self.principal.has_usable_password():
                errors["principal"] = "Machine principals must have an unusable password."
        if bool(self.revoked_at) != bool(self.revoked_by_id):
            errors["revoked_at"] = (
                "Revocation requires both a timestamp and a Super Admin actor."
            )
        if self.revoked_at and self.is_active:
            errors["is_active"] = "A revoked credential cannot remain active."
        if errors:
            raise ValidationError(errors)

    @property
    def is_expired(self):
        return bool(self.expires_at and self.expires_at <= timezone.now())

    @property
    def is_usable(self):
        return bool(
            self.is_active
            and self.revoked_at is None
            and not self.is_expired
            and self.principal_id
            and self.principal.is_active
            and not self.principal.role_id
            and not self.principal.has_usable_password()
        )

    def __str__(self):
        return f"{self.name} ({self.key_id})"


class AIIngestionCameraScope(BaseModel):
    """Explicitly permits one machine credential to use one Camera."""

    credential = models.ForeignKey(
        AIIngestionCredential,
        on_delete=models.PROTECT,
        related_name="camera_scopes",
    )
    camera = models.ForeignKey(
        Camera,
        on_delete=models.PROTECT,
        related_name="ai_ingestion_scopes",
    )

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["credential", "is_active"],
                name="ai_scope_credential_idx",
            ),
            models.Index(
                fields=["camera", "is_active"],
                name="ai_scope_camera_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["credential", "camera"],
                name="unique_ai_credential_camera_scope",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.credential_id and self.credential.revoked_at:
            errors["credential"] = "A revoked credential cannot receive camera scopes."
        if self.camera_id:
            if not self.camera.is_active:
                errors["camera"] = "Camera scopes require an active camera."
            elif not self.camera.facility.is_active:
                errors["camera"] = "Camera scopes require an active facility."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.credential.key_id}:{self.camera.code}"


CAMERA_EVENT_TYPE_VALUES = (
    "fire_alert",
    "smoke_alert",
    "intrusion_alert",
    "vehicle_entry",
    "vehicle_exit",
    "tamper_alert",
)
CAMERA_EVENT_VEHICLE_TYPE_VALUES = ("car", "truck", "van", "bus", "motorcycle")
CAMERA_EVENT_DIRECTION_VALUES = ("entry", "exit")
CAMERA_EVENT_TAMPER_TYPE_VALUES = (
    "camera_covered",
    "camera_moved",
    "signal_lost",
    "out_of_focus",
)


class CameraEvent(BaseModel):
    """Final confirmed event emitted by an external camera-processing service."""

    class EventType(models.TextChoices):
        FIRE_ALERT = "fire_alert", "Fire alert"
        SMOKE_ALERT = "smoke_alert", "Smoke alert"
        INTRUSION_ALERT = "intrusion_alert", "Intrusion alert"
        VEHICLE_ENTRY = "vehicle_entry", "Vehicle entry"
        VEHICLE_EXIT = "vehicle_exit", "Vehicle exit"
        TAMPER_ALERT = "tamper_alert", "Tamper alert"

    class VehicleType(models.TextChoices):
        CAR = "car", "Car"
        TRUCK = "truck", "Truck"
        VAN = "van", "Van"
        BUS = "bus", "Bus"
        MOTORCYCLE = "motorcycle", "Motorcycle"

    class Direction(models.TextChoices):
        ENTRY = "entry", "Entry"
        EXIT = "exit", "Exit"

    class TamperType(models.TextChoices):
        CAMERA_COVERED = "camera_covered", "Camera covered"
        CAMERA_MOVED = "camera_moved", "Camera moved"
        SIGNAL_LOST = "signal_lost", "Signal lost"
        OUT_OF_FOCUS = "out_of_focus", "Out of focus"

    event_type = models.CharField(max_length=30, choices=EventType.choices)
    camera = models.ForeignKey(
        Camera,
        on_delete=models.PROTECT,
        related_name="events",
    )
    ingestion_credential = models.ForeignKey(
        AIIngestionCredential,
        on_delete=models.PROTECT,
        related_name="camera_events",
    )
    roi = models.ForeignKey(
        CameraROI,
        on_delete=models.PROTECT,
        related_name="camera_events",
        null=True,
        blank=True,
    )
    source_event_id = models.UUIDField()
    track_id = models.CharField(max_length=255, null=True, blank=True)
    confidence = models.DecimalField(
        max_digits=7,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(Decimal("1")),
        ],
    )
    object_class = models.CharField(max_length=100, null=True, blank=True)
    detected_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    snapshot_path = models.FileField(
        storage=get_protected_storage,
        upload_to="",
        max_length=500,
        null=True,
        blank=True,
    )
    security_alert = models.OneToOneField(
        SecurityAlert,
        on_delete=models.PROTECT,
        related_name="camera_event",
        null=True,
        blank=True,
    )
    bbox = models.JSONField(null=True, blank=True)
    bbox_plate = models.JSONField(null=True, blank=True)
    bbox_vehicle = models.JSONField(null=True, blank=True)
    crossing_centroid = models.JSONField(null=True, blank=True)
    entered_roi_at = models.DateTimeField(null=True, blank=True)
    time_restricted = models.BooleanField(null=True, blank=True)
    plate_number = models.CharField(max_length=32, null=True, blank=True)
    plate_confidence = models.DecimalField(
        max_digits=7,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("1"))],
    )
    ocr_confidence = models.DecimalField(
        max_digits=7,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("1"))],
    )
    vehicle_type = models.CharField(
        max_length=20,
        choices=VehicleType.choices,
        null=True,
        blank=True,
    )
    vehicle_confidence = models.DecimalField(
        max_digits=7,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("1"))],
    )
    direction = models.CharField(
        max_length=10,
        choices=Direction.choices,
        null=True,
        blank=True,
    )
    authorized = models.BooleanField(null=True, blank=True)
    tamper_type = models.CharField(
        max_length=30,
        choices=TamperType.choices,
        null=True,
        blank=True,
    )

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["camera", "-detected_at"],
                name="cam_event_cam_detect_idx",
            ),
            models.Index(
                fields=["event_type", "-detected_at"],
                name="cam_event_type_detect_idx",
            ),
            models.Index(
                fields=["plate_number", "-detected_at"],
                name="cam_event_plate_detect_idx",
            ),
            models.Index(
                fields=["authorized", "event_type", "-detected_at"],
                name="cam_event_auth_type_det_idx",
            ),
            models.Index(
                fields=["tamper_type", "-detected_at"],
                name="cam_event_tamp_detect_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["ingestion_credential", "source_event_id"],
                name="unique_cam_event_source",
            ),
            models.CheckConstraint(
                check=Q(event_type__in=CAMERA_EVENT_TYPE_VALUES),
                name="cam_event_type_valid",
            ),
            models.CheckConstraint(
                check=Q(confidence__isnull=True)
                | Q(confidence__gte=0, confidence__lte=1),
                name="cam_event_confidence_range",
            ),
            models.CheckConstraint(
                check=Q(plate_confidence__isnull=True)
                | Q(plate_confidence__gte=0, plate_confidence__lte=1),
                name="cam_event_plate_conf_range",
            ),
            models.CheckConstraint(
                check=Q(ocr_confidence__isnull=True)
                | Q(ocr_confidence__gte=0, ocr_confidence__lte=1),
                name="cam_event_ocr_conf_range",
            ),
            models.CheckConstraint(
                check=Q(vehicle_confidence__isnull=True)
                | Q(vehicle_confidence__gte=0, vehicle_confidence__lte=1),
                name="cam_event_vehicle_conf_range",
            ),
            models.CheckConstraint(
                check=Q(duration_seconds__isnull=True) | Q(duration_seconds__gte=0),
                name="cam_event_duration_positive",
            ),
            models.CheckConstraint(
                check=Q(vehicle_type__isnull=True)
                | Q(vehicle_type__in=CAMERA_EVENT_VEHICLE_TYPE_VALUES),
                name="cam_event_vehicle_type_valid",
            ),
            models.CheckConstraint(
                check=Q(direction__isnull=True)
                | Q(direction__in=CAMERA_EVENT_DIRECTION_VALUES),
                name="cam_event_direction_valid",
            ),
            models.CheckConstraint(
                check=Q(tamper_type__isnull=True)
                | Q(tamper_type__in=CAMERA_EVENT_TAMPER_TYPE_VALUES),
                name="cam_event_tamper_type_valid",
            ),
        ]

    @property
    def facility(self):
        return self.camera.facility

    @property
    def status(self):
        if self.security_alert_id:
            return self.security_alert.status
        return "recorded"

    def __str__(self):
        return f"{self.event_type}:{self.camera.code}:{self.source_event_id}"


def safety_document_upload_path(instance, filename):
    extension = PurePosixPath(str(filename or "").replace("\\", "/")).suffix.lower()
    return f"security/documents/{instance.facility_id}/{uuid.uuid4().hex}{extension}"


class SafetyDocument(BaseModel):
    class Category(models.TextChoices):
        POLICY = "policy", "Policy"
        PROCEDURE = "procedure", "Procedure"
        PERMIT = "permit", "Permit"
        REPORT = "report", "Report"

    facility = models.ForeignKey("facilities.Facility", on_delete=models.PROTECT, related_name="safety_documents")
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=20, choices=Category.choices)
    file = models.FileField(upload_to=safety_document_upload_path, storage=get_protected_storage, validators=[validate_attachment_file])
    original_file_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=127)
    file_size = models.PositiveBigIntegerField()

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=["facility", "category", "-created_at"], name="safety_doc_fac_cat_idx")]
        constraints = [models.CheckConstraint(check=Q(file_size__gt=0), name="safety_document_size_positive")]

    def save(self, *args, **kwargs):
        if self.file and (self._state.adding or not self.file._committed):
            metadata = inspect_attachment_file(self.file)
            self.original_file_name = metadata.original_file_name
            self.mime_type = metadata.mime_type
            self.file_size = metadata.file_size
        self.full_clean()
        return super().save(*args, **kwargs)
