import json
import math
from decimal import Decimal
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q

from apps.common.models import BaseModel

from . import geo


HAZARD_PROVIDER_VALUES = ("usgs", "gdacs", "mhews")
HAZARD_TYPE_VALUES = (
    "earthquake",
    "tropical_cyclone",
    "flood",
    "volcano",
    "wildfire",
    "extreme_heat",
    "extreme_cold",
    "heavy_snow",
    "high_wind",
    "heavy_rain",
    # Dust and sand storms: no existing value represents them. Wind, rain and
    # heat all describe a different hazard to workers on site.
    "dust_storm",
)
HAZARD_ALERT_LEVEL_VALUES = ("green", "orange", "red")
HAZARD_PROVIDER_STATUS_VALUES = ("active", "withdrawn", "expired")
SAFETY_SEVERITY_VALUES = ("low", "medium", "high", "critical")
SAFETY_ALERT_STATUS_VALUES = ("new", "acknowledged", "actioned", "closed", "dismissed")
SAFETY_ACTION_VALUES = (
    "suspend_outdoor_work",
    "delay_shift",
    "modify_working_hours",
    "increase_precautions",
    "inspect_site",
    "monitor",
    "other",
)
# The system never recommends a free-text action; "other" is a human choice.
SYSTEM_RECOMMENDABLE_ACTION_VALUES = tuple(
    value for value in SAFETY_ACTION_VALUES if value != "other"
)

# Public event pages that may be linked from a HazardEvent. Anything else is
# rejected so provider-supplied URLs cannot point users at arbitrary hosts.
SOURCE_URL_ALLOWED_HOSTS = {
    "usgs": {"earthquake.usgs.gov"},
    "gdacs": {"www.gdacs.org", "gdacs.org"},
    "mhews": {"climweb.med.gov.sy"},
}
SAFETY_TELEGRAM_DELIVERY_STATUS_VALUES = (
    "queued",
    "processing",
    "sent",
    "failed",
    "skipped",
)
# Two separate protective workflows with different owners and different
# consequences. Worker protection reaches people and is the only kind that can
# produce an outbound instruction; asset protection is recorded and audited.
SAFETY_DECISION_TYPE_VALUES = ("worker_protection", "asset_protection")
SAFETY_PROPOSAL_STATUS_VALUES = ("pending_manager_review", "approved", "rejected")
# Telegram chat ids are integers; group and channel ids are negative. Nothing
# else is accepted, so a phone number or @username can never reach the API.
TELEGRAM_CHAT_ID_PATTERN = r"^-?[0-9]{5,20}$"
TELEGRAM_CHAT_ID_MAX_LENGTH = 32
TELEGRAM_EVENT_KEY_MAX_LENGTH = 120

HAZARD_PAYLOAD_MAX_BYTES = 32 * 1024
_PAYLOAD_MAX_KEY_LENGTH = 64
_PAYLOAD_MAX_STRING_LENGTH = 1000
_PAYLOAD_MAX_LIST_ITEMS = 50
_PAYLOAD_MAX_DEPTH = 3
_PAYLOAD_SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "password",
    "passwd",
    "apikey",
    "api_key",
    "authorization",
    "auth",
    "signature",
    "credential",
    "cookie",
    "session",
)


def validate_source_url(url, provider):
    """Require an https URL on the provider's allowlisted public host."""

    if not url:
        return
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise ValidationError({"source_url": "The source URL is invalid."}) from exc
    allowed_hosts = SOURCE_URL_ALLOWED_HOSTS.get(provider, set())
    if (
        parts.scheme != "https"
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
        or (parts.hostname or "").lower() not in allowed_hosts
    ):
        raise ValidationError(
            {"source_url": "The source URL must be an https link to the provider site."}
        )


def _digits(value):
    return "".join(character for character in str(value or "") if character.isdigit())


def _is_sensitive_key(key):
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in _PAYLOAD_SENSITIVE_KEY_PARTS)


def _sanitize_payload_value(value, depth):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return str(value) if value.is_finite() else None
    if isinstance(value, str):
        return value[:_PAYLOAD_MAX_STRING_LENGTH]
    if depth >= _PAYLOAD_MAX_DEPTH:
        return None
    if isinstance(value, (list, tuple)):
        return [
            _sanitize_payload_value(item, depth + 1)
            for item in list(value)[:_PAYLOAD_MAX_LIST_ITEMS]
        ]
    if isinstance(value, dict):
        return _sanitize_payload_mapping(value, depth + 1)
    return None


def _sanitize_payload_mapping(mapping, depth):
    sanitized = {}
    for key, value in mapping.items():
        if not isinstance(key, str) or not key or len(key) > _PAYLOAD_MAX_KEY_LENGTH:
            continue
        if _is_sensitive_key(key):
            continue
        sanitized[key] = _sanitize_payload_value(value, depth)
    return sanitized


def sanitize_hazard_payload(payload):
    """Return a bounded, secret-free JSON subset of provider properties.

    Keys that look like credentials are dropped, strings and lists are capped,
    nesting is limited, and an oversized result is replaced with a marker so
    one verbose provider item can never block ingestion or bloat the table.
    """

    if not isinstance(payload, dict):
        return {}
    sanitized = _sanitize_payload_mapping(payload, 0)
    if payload_size_bytes(sanitized) > HAZARD_PAYLOAD_MAX_BYTES:
        return {"payload_truncated": True}
    return sanitized


def payload_size_bytes(payload):
    return len(json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8"))


class HazardEvent(BaseModel):
    """A normalized external hazard fact reported by a provider.

    Providers only report facts. Whether any project is affected, and how
    severely, is decided by SFLMS policy when alerts are evaluated.
    """

    class Provider(models.TextChoices):
        USGS = "usgs", "USGS"
        GDACS = "gdacs", "GDACS"
        # Syrian Ministry of Emergency and Disaster Management, Multi-Hazard
        # Early Warning System. Registered here so the adapter can be added;
        # no MHEWS adapter, polling, or policy exists yet.
        MHEWS = "mhews", "MHEWS (Syria)"

    class HazardType(models.TextChoices):
        EARTHQUAKE = "earthquake", "Earthquake"
        TROPICAL_CYCLONE = "tropical_cyclone", "Tropical cyclone"
        FLOOD = "flood", "Flood"
        VOLCANO = "volcano", "Volcano"
        WILDFIRE = "wildfire", "Wildfire"
        EXTREME_HEAT = "extreme_heat", "Extreme heat"
        EXTREME_COLD = "extreme_cold", "Extreme cold"
        HEAVY_SNOW = "heavy_snow", "Heavy snow"
        HIGH_WIND = "high_wind", "High wind"
        HEAVY_RAIN = "heavy_rain", "Heavy rain"
        DUST_STORM = "dust_storm", "Dust or sand storm"

    class AlertLevel(models.TextChoices):
        GREEN = "green", "Green"
        ORANGE = "orange", "Orange"
        RED = "red", "Red"

    class ProviderStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        WITHDRAWN = "withdrawn", "Withdrawn"
        EXPIRED = "expired", "Expired"

    provider = models.CharField(max_length=20, choices=Provider.choices)
    provider_event_id = models.CharField(max_length=128)
    hazard_type = models.CharField(max_length=30, choices=HazardType.choices)
    provider_severity = models.CharField(max_length=32, blank=True, default="")
    alert_level = models.CharField(
        max_length=10,
        choices=AlertLevel.choices,
        null=True,
        blank=True,
    )
    magnitude = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("-2")), MaxValueValidator(Decimal("10"))],
    )
    depth_km = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("-15")), MaxValueValidator(Decimal("1000"))],
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("-90")), MaxValueValidator(Decimal("90"))],
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("-180")), MaxValueValidator(Decimal("180"))],
    )
    radius_km = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(Decimal("2000"))],
    )
    title = models.CharField(max_length=255)
    source_url = models.CharField(max_length=500, blank=True, default="")
    occurred_at = models.DateTimeField()
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    provider_updated_at = models.DateTimeField()
    provider_status = models.CharField(
        max_length=20,
        choices=ProviderStatus.choices,
        default=ProviderStatus.ACTIVE,
    )
    revision = models.PositiveIntegerField(default=1)
    last_seen_at = models.DateTimeField()
    payload = models.JSONField(default=dict, blank=True)
    # Optional authoritative warned area, in canonical GeoJSON MultiPolygon
    # coordinate form ([longitude, latitude] positions). NULL means this
    # hazard uses the original point+radius geometry, which is unchanged.
    # When present, matching is exact containment and `radius_km` is not used
    # to match; `latitude`/`longitude` remain the event's reference point for
    # display and audit only. Validated in `clean()`, like `payload`.
    area_polygons = models.JSONField(null=True, blank=True, default=None)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["hazard_type", "-occurred_at"], name="hazard_type_occurred_idx"),
            models.Index(
                fields=["provider", "-provider_updated_at"],
                name="hazard_provider_updated_idx",
            ),
            models.Index(
                fields=["provider_status", "occurred_at"],
                name="hazard_status_occurred_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_event_id"],
                name="unique_hazard_provider_event",
            ),
            models.CheckConstraint(
                check=Q(provider__in=HAZARD_PROVIDER_VALUES),
                name="hazard_provider_valid",
            ),
            models.CheckConstraint(
                check=Q(hazard_type__in=HAZARD_TYPE_VALUES),
                name="hazard_type_valid",
            ),
            models.CheckConstraint(
                check=Q(alert_level__isnull=True) | Q(alert_level__in=HAZARD_ALERT_LEVEL_VALUES),
                name="hazard_alert_level_valid",
            ),
            models.CheckConstraint(
                check=Q(provider_status__in=HAZARD_PROVIDER_STATUS_VALUES),
                name="hazard_provider_status_valid",
            ),
            models.CheckConstraint(
                check=~Q(provider_event_id=""),
                name="hazard_provider_event_id_required",
            ),
            models.CheckConstraint(check=~Q(title=""), name="hazard_title_required"),
            models.CheckConstraint(
                check=Q(latitude__gte=Decimal("-90"), latitude__lte=Decimal("90")),
                name="hazard_latitude_range",
            ),
            models.CheckConstraint(
                check=Q(longitude__gte=Decimal("-180"), longitude__lte=Decimal("180")),
                name="hazard_longitude_range",
            ),
            models.CheckConstraint(
                check=Q(magnitude__isnull=True)
                | Q(magnitude__gte=Decimal("-2"), magnitude__lte=Decimal("10")),
                name="hazard_magnitude_range",
            ),
            models.CheckConstraint(
                check=Q(radius_km__isnull=True)
                | Q(radius_km__gt=Decimal("0"), radius_km__lte=Decimal("2000")),
                name="hazard_radius_range",
            ),
            models.CheckConstraint(check=Q(revision__gte=1), name="hazard_revision_positive"),
            models.CheckConstraint(
                check=Q(valid_from__isnull=True)
                | Q(valid_until__isnull=True)
                | Q(valid_until__gte=models.F("valid_from")),
                name="hazard_validity_window_valid",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        self.provider_event_id = (self.provider_event_id or "").strip()
        self.title = (self.title or "").strip()[:255]
        if not self.provider_event_id:
            errors["provider_event_id"] = "A provider event identifier is required."
        if not self.title:
            errors["title"] = "A hazard title is required."
        try:
            validate_source_url(self.source_url, self.provider)
        except ValidationError as exc:
            errors.update(exc.message_dict)
        if not isinstance(self.payload, dict):
            errors["payload"] = "The hazard payload must be an object."
        elif payload_size_bytes(self.payload) > HAZARD_PAYLOAD_MAX_BYTES:
            errors["payload"] = "The hazard payload exceeds the permitted size."
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            errors["valid_until"] = "The validity window end cannot precede its start."
        if self.area_polygons is not None:
            try:
                # Store the canonical MultiPolygon form so every reader sees
                # one shape; malformed geometry is rejected, never approximated.
                self.area_polygons = geo.normalize_multipolygon(self.area_polygons)
            except geo.InvalidGeometry as exc:
                errors["area_polygons"] = str(exc)
        if errors:
            raise ValidationError(errors)

    @property
    def has_area_geometry(self):
        """True when this hazard carries an authoritative warned area."""

        return bool(self.area_polygons)

    def __str__(self):
        return f"{self.provider}:{self.provider_event_id}"


class HazardEventAlias(BaseModel):
    """Another provider identifier that denotes an existing hazard.

    Some providers give each revision of a warning its own identifier and link
    it to the previous one by reference (CAP ``Update``/``Cancel``). A feed only
    exposes a rolling window, so a later revision can arrive in a polling cycle
    that no longer contains the original message. Recording every identifier a
    chain has used lets the next revision resolve to the hazard that already
    exists instead of creating a second one.

    Identity only ever comes from provider identifiers. Nothing here is
    inferred from geometry, timing, wording, or similarity of any kind.

    Providers that use one stable identifier per event (USGS, GDACS) never
    write rows here and are entirely unaffected.
    """

    provider = models.CharField(max_length=20, choices=HazardEvent.Provider.choices)
    alias_identifier = models.CharField(max_length=128)
    hazard_event = models.ForeignKey(
        HazardEvent,
        on_delete=models.CASCADE,
        related_name="identity_aliases",
    )

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["provider", "alias_identifier"],
                name="hazard_alias_lookup_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "alias_identifier"],
                name="unique_hazard_alias_identifier",
            ),
            models.CheckConstraint(
                check=Q(provider__in=HAZARD_PROVIDER_VALUES),
                name="hazard_alias_provider_valid",
            ),
            models.CheckConstraint(
                check=~Q(alias_identifier=""),
                name="hazard_alias_identifier_required",
            ),
        ]

    def __str__(self):
        return f"{self.provider}:{self.alias_identifier}"


class ProjectSafetyAlert(BaseModel):
    """A project-scoped safety alert that a human manager must act on.

    Only the ingestion service creates these rows. Recommended actions are
    advisory; the system never suspends, evacuates, cancels, or messages
    workers on its own.
    """

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        NEW = "new", "New"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        ACTIONED = "actioned", "Actioned"
        CLOSED = "closed", "Closed"
        DISMISSED = "dismissed", "Dismissed"

    class Action(models.TextChoices):
        SUSPEND_OUTDOOR_WORK = "suspend_outdoor_work", "Suspend outdoor work"
        DELAY_SHIFT = "delay_shift", "Delay shift"
        MODIFY_WORKING_HOURS = "modify_working_hours", "Modify working hours"
        INCREASE_PRECAUTIONS = "increase_precautions", "Increase precautions"
        INSPECT_SITE = "inspect_site", "Inspect site"
        MONITOR = "monitor", "Monitor"
        OTHER = "other", "Other"

    immutable_fields = (
        "project_id",
        "hazard_event_id",
        "hazard_type",
        "project_latitude",
        "project_longitude",
        "created_at",
    )

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        related_name="safety_alerts",
    )
    hazard_event = models.ForeignKey(
        HazardEvent,
        on_delete=models.PROTECT,
        related_name="project_alerts",
    )
    hazard_type = models.CharField(max_length=30, choices=HazardEvent.HazardType.choices)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    distance_km = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    project_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("-90")), MaxValueValidator(Decimal("90"))],
    )
    project_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("-180")), MaxValueValidator(Decimal("180"))],
    )
    rule_code = models.CharField(max_length=100)
    policy_version = models.PositiveIntegerField(default=0)
    recommended_action = models.CharField(max_length=30, choices=Action.choices)
    acknowledged_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="acknowledged_safety_alerts",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    decision = models.CharField(
        max_length=30,
        choices=Action.choices,
        null=True,
        blank=True,
    )
    decision_notes = models.TextField(blank=True, default="")
    decided_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="decided_safety_alerts",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True, default="")
    resolved_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="resolved_safety_alerts",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    hazard_withdrawn_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["project", "status", "-created_at"],
                name="safety_alert_proj_status_idx",
            ),
            models.Index(fields=["status", "severity"], name="safety_alert_status_sev_idx"),
            models.Index(fields=["-created_at"], name="safety_alert_created_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "hazard_event"],
                name="unique_safety_alert_project_hazard",
            ),
            models.CheckConstraint(
                check=Q(hazard_type__in=HAZARD_TYPE_VALUES),
                name="safety_alert_hazard_type_valid",
            ),
            models.CheckConstraint(
                check=Q(severity__in=SAFETY_SEVERITY_VALUES),
                name="safety_alert_severity_valid",
            ),
            models.CheckConstraint(
                check=Q(status__in=SAFETY_ALERT_STATUS_VALUES),
                name="safety_alert_status_valid",
            ),
            models.CheckConstraint(
                check=Q(recommended_action__in=SYSTEM_RECOMMENDABLE_ACTION_VALUES),
                name="safety_alert_recommendation_valid",
            ),
            models.CheckConstraint(
                check=Q(decision__isnull=True) | Q(decision__in=SAFETY_ACTION_VALUES),
                name="safety_alert_decision_valid",
            ),
            models.CheckConstraint(
                check=Q(distance_km__gte=Decimal("0")),
                name="safety_alert_distance_positive",
            ),
            models.CheckConstraint(
                check=Q(
                    project_latitude__gte=Decimal("-90"),
                    project_latitude__lte=Decimal("90"),
                    project_longitude__gte=Decimal("-180"),
                    project_longitude__lte=Decimal("180"),
                ),
                name="safety_alert_project_coords_range",
            ),
            models.CheckConstraint(
                check=(
                    Q(acknowledged_by__isnull=True, acknowledged_at__isnull=True)
                    | Q(acknowledged_by__isnull=False, acknowledged_at__isnull=False)
                ),
                name="safety_alert_ack_fields_paired",
            ),
            models.CheckConstraint(
                check=(
                    Q(decision__isnull=True, decided_by__isnull=True, decided_at__isnull=True)
                    | Q(decision__isnull=False, decided_by__isnull=False, decided_at__isnull=False)
                ),
                name="safety_alert_decision_fields_paired",
            ),
            models.CheckConstraint(
                check=(
                    Q(resolved_by__isnull=True, resolved_at__isnull=True)
                    | Q(resolved_by__isnull=False, resolved_at__isnull=False)
                ),
                name="safety_alert_resolution_paired",
            ),
            models.CheckConstraint(
                check=~Q(decision="other") | ~Q(decision_notes=""),
                name="safety_alert_other_needs_notes",
            ),
            models.CheckConstraint(
                check=(
                    Q(
                        status="new",
                        acknowledged_at__isnull=True,
                        decision__isnull=True,
                        resolved_at__isnull=True,
                    )
                    | Q(
                        status="acknowledged",
                        acknowledged_at__isnull=False,
                        decision__isnull=True,
                        resolved_at__isnull=True,
                    )
                    | Q(
                        status="actioned",
                        acknowledged_at__isnull=False,
                        decision__isnull=False,
                        resolved_at__isnull=True,
                    )
                    | Q(
                        status="closed",
                        decision__isnull=False,
                        resolved_at__isnull=False,
                    )
                    | (
                        Q(status="dismissed", decision__isnull=True, resolved_at__isnull=False)
                        & ~Q(resolution_notes="")
                    )
                ),
                name="safety_alert_status_fields_valid",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.hazard_event_id and self.hazard_type != self.hazard_event.hazard_type:
            errors["hazard_type"] = "The alert hazard type must match its hazard event."
        if self.decision == self.Action.OTHER and not (self.decision_notes or "").strip():
            errors["decision_notes"] = "Notes are required when the decision is 'other'."
        if self.status == self.Status.DISMISSED and not (self.resolution_notes or "").strip():
            errors["resolution_notes"] = "A dismissal reason is required."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self._state.adding and self.pk:
            original = self.__class__.all_objects.filter(pk=self.pk).first()
            if original is not None:
                changed = [
                    field_name
                    for field_name in self.immutable_fields
                    if getattr(original, field_name) != getattr(self, field_name)
                ]
                if changed:
                    raise ValidationError(
                        "Safety alert snapshot fields cannot be changed: " + ", ".join(changed)
                    )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Safety alerts cannot be hard-deleted.")

    def __str__(self):
        return f"{self.hazard_type} safety alert for project {self.project_id}"


class SafetyActionProposal(BaseModel):
    """A protective action one manager proposes and the General Manager rules on.

    An external hazard is information, never an instruction. Nothing here is
    acted on, messaged, or dispatched while it sits at
    ``pending_manager_review``: only an approval by a General Manager / Super
    Admin turns a proposal into an accepted decision, and only a
    ``worker_protection`` approval can reach a person.

    The two decision types are kept apart on purpose. Worker protection is
    proposed by the Construction Manager responsible for the project's site
    personnel; asset protection is proposed by the Operations Manager
    responsible for the facility's equipment. Neither can propose the other's
    kind, and neither can rule on their own proposal.
    """

    class DecisionType(models.TextChoices):
        WORKER_PROTECTION = "worker_protection", "Worker protection"
        ASSET_PROTECTION = "asset_protection", "Asset protection"

    class Status(models.TextChoices):
        PENDING_MANAGER_REVIEW = "pending_manager_review", "Pending manager review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    immutable_fields = (
        "alert_id",
        "decision_type",
        "proposed_by_id",
        "created_at",
    )

    alert = models.ForeignKey(
        ProjectSafetyAlert,
        on_delete=models.PROTECT,
        related_name="action_proposals",
    )
    decision_type = models.CharField(max_length=20, choices=DecisionType.choices)
    proposed_action = models.CharField(
        max_length=30,
        choices=ProjectSafetyAlert.Action.choices,
    )
    proposal_notes = models.TextField(
        help_text="The proposing manager's justification. Always required.",
    )
    # The window the proposed action would apply for. Optional: some actions
    # ("inspect site") have no duration, and the approver should see an honest
    # blank rather than an invented one.
    effective_from = models.DateTimeField(null=True, blank=True)
    effective_until = models.DateTimeField(null=True, blank=True)
    worker_scope = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=(
            "Which people the action covers, e.g. 'outdoor crews on level 3'. "
            "Worker protection only."
        ),
    )
    status = models.CharField(
        max_length=25,
        choices=Status.choices,
        default=Status.PENDING_MANAGER_REVIEW,
    )
    affected_assets = models.ManyToManyField(
        "assets.Asset",
        blank=True,
        related_name="safety_action_proposals",
        help_text="Asset-protection scope. Never populated for worker protection.",
    )
    proposed_by = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        related_name="proposed_safety_actions",
    )
    proposed_at = models.DateTimeField()
    reviewed_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_safety_actions",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["status", "-proposed_at"],
                name="safety_proposal_status_idx",
            ),
            models.Index(
                fields=["alert", "decision_type", "status"],
                name="safety_proposal_alert_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(decision_type__in=SAFETY_DECISION_TYPE_VALUES),
                name="safety_proposal_decision_type_valid",
            ),
            models.CheckConstraint(
                check=Q(status__in=SAFETY_PROPOSAL_STATUS_VALUES),
                name="safety_proposal_status_valid",
            ),
            models.CheckConstraint(
                check=Q(proposed_action__in=SAFETY_ACTION_VALUES),
                name="safety_proposal_action_valid",
            ),
            # A ruling always records who made it and when; an open proposal
            # never carries a reviewer. Keeps "who decided this" answerable.
            models.CheckConstraint(
                check=(
                    Q(status="pending_manager_review", reviewed_by__isnull=True, reviewed_at__isnull=True)
                    | Q(reviewed_by__isnull=False, reviewed_at__isnull=False)
                ),
                name="safety_proposal_review_fields_consistent",
            ),
            # At most one open proposal of each kind per alert, so an approver
            # is never shown two competing pending asks for the same decision.
            models.UniqueConstraint(
                fields=["alert", "decision_type"],
                condition=Q(status="pending_manager_review", is_active=True),
                name="unique_open_safety_proposal_per_alert_type",
            ),
            models.CheckConstraint(
                check=(
                    Q(effective_from__isnull=True)
                    | Q(effective_until__isnull=True)
                    | Q(effective_until__gt=F("effective_from"))
                ),
                name="safety_proposal_window_ordered",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        notes = (self.proposal_notes or "").strip()
        if not notes:
            errors["proposal_notes"] = "A justification is required."
        if self.status == self.Status.REJECTED and not (self.review_notes or "").strip():
            errors["review_notes"] = "A rejection reason is required."
        if (
            self.effective_from
            and self.effective_until
            and self.effective_until <= self.effective_from
        ):
            errors["effective_until"] = "The end of the window must be after its start."
        if self.worker_scope and self.decision_type != self.DecisionType.WORKER_PROTECTION:
            errors["worker_scope"] = "Worker scope applies to worker protection only."
        if errors:
            raise ValidationError(errors)

    @property
    def is_open(self):
        return self.status == self.Status.PENDING_MANAGER_REVIEW

    def __str__(self):
        return f"{self.get_decision_type_display()} proposal ({self.status})"


class ProjectTelegramDestination(BaseModel):
    """Where one project's approved worker instructions are delivered.

    Worker instructions are addressed to the *project*, not to individuals: an
    approved decision goes to the crew channel of each affected project and
    nowhere else. A project with no destination simply receives nothing, which
    is recorded rather than silently ignored.

    Provisioned by a Super Admin through Django Admin. The chat id is a numeric
    Telegram identifier obtained from Telegram itself; the platform never
    discovers, guesses or derives one, and this link is outbound only.
    """

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        related_name="telegram_destinations",
    )
    chat_id = models.CharField(
        max_length=TELEGRAM_CHAT_ID_MAX_LENGTH,
        validators=[
            RegexValidator(
                regex=TELEGRAM_CHAT_ID_PATTERN,
                message="Enter a numeric Telegram chat id (5-20 digits, optionally negative).",
            )
        ],
        help_text="Numeric Telegram chat/group/channel id. Never a phone number or an @username.",
    )
    display_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Human label for this destination, e.g. 'Site A crew channel'.",
    )
    is_enabled = models.BooleanField(default=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["project", "is_enabled"],
                name="safety_tg_dest_project_idx",
            ),
        ]
        constraints = [
            # One row per destination per project, so a single approval can
            # never fan out into duplicate messages to the same channel.
            models.UniqueConstraint(
                fields=["project", "chat_id"],
                name="unique_project_telegram_destination",
            ),
            models.CheckConstraint(
                check=Q(chat_id__regex=TELEGRAM_CHAT_ID_PATTERN),
                name="project_telegram_chat_id_format",
            ),
        ]

    def clean(self):
        super().clean()
        chat_id = (self.chat_id or "").strip()
        if chat_id != self.chat_id:
            self.chat_id = chat_id

    def __str__(self):
        return self.display_name or f"Telegram destination for project {self.project_id}"


class SafetyTelegramRecipient(BaseModel):
    """One person's Telegram destination for outbound safety messages.

    Provisioned exclusively by a Super Admin in Django Admin. A chat id is a
    numeric Telegram identifier the user obtains from Telegram itself; phone
    numbers and @usernames are not chat ids and are rejected. The platform
    never discovers, guesses, or derives a chat id, and never receives
    anything from Telegram: this destination is outbound only.

    This addresses responsible *managers* for recorded-decision messages, by
    virtue of their alert scope. Approved worker instructions do not come here:
    they are addressed to the affected project's crew channel, which is
    :class:`ProjectTelegramDestination`. Keeping the two apart means one routing
    rule per audience rather than two overlapping ones.
    """

    user = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        related_name="safety_telegram_recipients",
    )
    chat_id = models.CharField(
        max_length=TELEGRAM_CHAT_ID_MAX_LENGTH,
        unique=True,
        validators=[
            RegexValidator(
                regex=TELEGRAM_CHAT_ID_PATTERN,
                message="Enter a numeric Telegram chat id (5-20 digits, optionally negative).",
            )
        ],
        help_text="Numeric Telegram chat id. Never a phone number or an @username.",
    )
    is_enabled = models.BooleanField(default=True)

    class Meta(BaseModel.Meta):
        constraints = [
            # One destination per user, so a single decision can never fan out
            # into duplicate Telegram messages for the same person.
            models.UniqueConstraint(
                fields=["user"],
                name="unique_safety_telegram_recipient_user",
            ),
            models.CheckConstraint(
                check=Q(chat_id__regex=TELEGRAM_CHAT_ID_PATTERN),
                name="safety_telegram_chat_id_format",
            ),
        ]

    def clean(self):
        super().clean()
        chat_id = (self.chat_id or "").strip()
        if chat_id != self.chat_id:
            self.chat_id = chat_id
        if not chat_id:
            return
        # A phone number is not a chat id; catching the most likely mistake
        # here keeps a private number out of an outbound send attempt.
        phone_digits = _digits(getattr(self.user, "phone", "") if self.user_id else "")
        if phone_digits and phone_digits == _digits(chat_id):
            raise ValidationError(
                {"chat_id": "A phone number cannot be used as a Telegram chat id."}
            )

    def __str__(self):
        return f"Telegram destination for user {self.user_id}"


class SafetyTelegramDelivery(BaseModel):
    """One outbound Telegram send attempt for one recipient and one decision.

    Rows exist only after a human recorded a decision on a safety alert. The
    unique ``(alert, recipient, event_key)`` triple makes delivery idempotent
    under at-least-once task execution, so a retried or duplicated task can
    never send the same decision twice.
    """

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    alert = models.ForeignKey(
        ProjectSafetyAlert,
        on_delete=models.PROTECT,
        related_name="telegram_deliveries",
    )
    project_destination = models.ForeignKey(
        ProjectTelegramDestination,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="telegram_deliveries",
        help_text=(
            "Set for an approved worker instruction, which is addressed to the "
            "affected project's channel. Mutually exclusive with `recipient`."
        ),
    )
    recipient = models.ForeignKey(
        SafetyTelegramRecipient,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="deliveries",
    )
    proposal = models.ForeignKey(
        SafetyActionProposal,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="telegram_deliveries",
        help_text=(
            "Set for an approved worker-protection instruction. Null for a "
            "recorded-decision message to responsible managers."
        ),
    )
    notification = models.ForeignKey(
        "notifications.Notification",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="safety_telegram_deliveries",
    )
    event_key = models.CharField(max_length=TELEGRAM_EVENT_KEY_MAX_LENGTH)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    failure_code = models.CharField(max_length=64, blank=True, default="")
    provider_message_id = models.CharField(max_length=64, blank=True, default="")
    processing_started_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["status", "updated_at"], name="safety_tg_delivery_state_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["alert", "recipient", "event_key"],
                name="unique_safety_telegram_delivery_event",
            ),
            # The same idempotency rule for the project-addressed audience: one
            # row per (alert, destination, event), so a replayed task or a
            # duplicated commit hook can never send a channel a second copy.
            models.UniqueConstraint(
                fields=["alert", "project_destination", "event_key"],
                name="unique_safety_telegram_delivery_destination_event",
            ),
            # Exactly one audience per row, so "who was this sent to" is always
            # answerable from the row itself.
            models.CheckConstraint(
                check=(
                    Q(recipient__isnull=False, project_destination__isnull=True)
                    | Q(recipient__isnull=True, project_destination__isnull=False)
                ),
                name="safety_tg_delivery_single_audience",
            ),
            models.CheckConstraint(
                check=Q(status__in=SAFETY_TELEGRAM_DELIVERY_STATUS_VALUES),
                name="safety_tg_delivery_status_valid",
            ),
            models.CheckConstraint(
                check=~Q(event_key=""),
                name="safety_tg_delivery_event_key_present",
            ),
            models.CheckConstraint(
                check=(
                    Q(status="sent", sent_at__isnull=False)
                    | (~Q(status="sent") & Q(sent_at__isnull=True))
                ),
                name="safety_tg_delivery_sent_at_paired",
            ),
        ]

    def __str__(self):
        return f"Telegram delivery {self.status} for alert {self.alert_id}"
