"""Safety domain services: hazard ingestion and the human alert workflow.

Ingestion is the only path that creates HazardEvent and ProjectSafetyAlert
rows. Providers (a later phase) hand this module ``NormalizedHazardEvent``
values; they never create alerts themselves.
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services import record_audit
from apps.projects.models import Project

from . import geo, policy as safety_policy
from .models import (
    HAZARD_ALERT_LEVEL_VALUES,
    HAZARD_PROVIDER_STATUS_VALUES,
    HAZARD_PROVIDER_VALUES,
    HAZARD_TYPE_VALUES,
    SAFETY_ACTION_VALUES,
    HazardEvent,
    HazardEventAlias,
    ProjectSafetyAlert,
    sanitize_hazard_payload,
)
from .notifications import (
    KIND_CREATED,
    KIND_ESCALATED,
    KIND_WITHDRAWN,
    schedule_alert_notifications,
)
from .recipients import user_can_approve_safety, user_can_manage_alert
from .telegram_delivery import schedule_decision_delivery


logger = logging.getLogger(__name__)

MAX_NOTES_LENGTH = 2000
OPEN_ALERT_STATUSES = (
    ProjectSafetyAlert.Status.NEW,
    ProjectSafetyAlert.Status.ACKNOWLEDGED,
    ProjectSafetyAlert.Status.ACTIONED,
)
ACTION_ACKNOWLEDGE = "acknowledge"
ACTION_DECIDE = "decide"
ACTION_DISMISS = "dismiss"
ACTION_CLOSE = "close"
AVAILABLE_ACTIONS_BY_STATUS = {
    ProjectSafetyAlert.Status.NEW: (ACTION_ACKNOWLEDGE, ACTION_DISMISS),
    ProjectSafetyAlert.Status.ACKNOWLEDGED: (ACTION_DECIDE, ACTION_DISMISS),
    ProjectSafetyAlert.Status.ACTIONED: (ACTION_DECIDE, ACTION_CLOSE),
    ProjectSafetyAlert.Status.CLOSED: (),
    ProjectSafetyAlert.Status.DISMISSED: (),
}


# ---------------------------------------------------------------------------
# Ingestion contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizedHazardEvent:
    provider: str
    provider_event_id: str
    hazard_type: str
    title: str
    latitude: Decimal
    longitude: Decimal
    occurred_at: object
    provider_updated_at: object
    provider_severity: str = ""
    alert_level: str | None = None
    magnitude: Decimal | None = None
    depth_km: Decimal | None = None
    radius_km: Decimal | None = None
    source_url: str = ""
    valid_from: object = None
    valid_until: object = None
    provider_status: str = HazardEvent.ProviderStatus.ACTIVE
    payload: dict = field(default_factory=dict)
    # Optional authoritative warned area (Phase 6B). When present it, not
    # radius_km, decides which projects are affected.
    area_polygons: object = None
    # Every provider identifier this logical event has used, so a later
    # revision resolves to the same hazard across polling cycles. Providers
    # with one stable identifier per event leave this empty.
    identity_aliases: tuple = ()
    # True when the record revises an event that must already exist. Such a
    # record never creates a hazard: if its identity cannot be resolved, it is
    # ignored rather than duplicated.
    revision_of_existing: bool = False


@dataclass
class IngestionResult:
    enabled: bool = True
    received: int = 0
    events_created: int = 0
    events_updated: int = 0
    events_unchanged: int = 0
    events_ignored: int = 0
    stale_updates_ignored: int = 0
    invalid_skipped: int = 0
    alerts_created: int = 0
    alerts_escalated: int = 0
    alerts_withdrawn: int = 0


def _decimal(value, name, *, places):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValidationError({name: "Must be numeric."})
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError({name: "Must be numeric."}) from exc
    if not number.is_finite():
        raise ValidationError({name: "Must be finite."})
    return number.quantize(Decimal(1).scaleb(-places))


def _aware(value, name, *, required):
    if value is None:
        if required:
            raise ValidationError({name: "A timestamp is required."})
        return None
    if not hasattr(value, "utcoffset") or timezone.is_naive(value):
        raise ValidationError({name: "Timestamps must be timezone-aware."})
    return value


def _validated_area(area_polygons):
    """Canonicalize optional warned-area geometry, or raise ValidationError.

    Malformed geometry is rejected outright rather than degraded into an
    approximate shape, so a bad polygon can never widen a warned area.
    """

    if area_polygons is None:
        return None
    try:
        return geo.normalize_multipolygon(area_polygons)
    except geo.InvalidGeometry as exc:
        raise ValidationError({"area_polygons": str(exc)}) from exc


def _validated_fields(event):
    """Normalize a provider event into model field values or raise."""

    if not isinstance(event, NormalizedHazardEvent):
        raise ValidationError({"event": "Unsupported hazard event contract."})
    errors = {}
    if event.provider not in HAZARD_PROVIDER_VALUES:
        errors["provider"] = "Unsupported provider."
    if event.hazard_type not in HAZARD_TYPE_VALUES:
        errors["hazard_type"] = "Unsupported hazard type."
    if event.alert_level is not None and event.alert_level not in HAZARD_ALERT_LEVEL_VALUES:
        errors["alert_level"] = "Unsupported alert level."
    if event.provider_status not in HAZARD_PROVIDER_STATUS_VALUES:
        errors["provider_status"] = "Unsupported provider status."
    if not isinstance(event.provider_event_id, str) or not event.provider_event_id.strip():
        errors["provider_event_id"] = "A provider event identifier is required."
    elif len(event.provider_event_id.strip()) > 128:
        errors["provider_event_id"] = "The provider event identifier is too long."
    if not isinstance(event.title, str) or not event.title.strip():
        errors["title"] = "A hazard title is required."
    if errors:
        raise ValidationError(errors)
    values = {
        "provider": event.provider,
        "provider_event_id": event.provider_event_id.strip(),
        "hazard_type": event.hazard_type,
        "title": event.title.strip()[:255],
        "provider_severity": str(event.provider_severity or "")[:32],
        "alert_level": event.alert_level,
        "latitude": _decimal(event.latitude, "latitude", places=6),
        "longitude": _decimal(event.longitude, "longitude", places=6),
        "magnitude": _decimal(event.magnitude, "magnitude", places=2),
        "depth_km": _decimal(event.depth_km, "depth_km", places=2),
        "radius_km": _decimal(event.radius_km, "radius_km", places=2),
        "source_url": str(event.source_url or "")[:500],
        "occurred_at": _aware(event.occurred_at, "occurred_at", required=True),
        "valid_from": _aware(event.valid_from, "valid_from", required=False),
        "valid_until": _aware(event.valid_until, "valid_until", required=False),
        "provider_updated_at": _aware(
            event.provider_updated_at, "provider_updated_at", required=True
        ),
        "provider_status": event.provider_status,
        "payload": sanitize_hazard_payload(event.payload),
        "area_polygons": _validated_area(event.area_polygons),
    }
    if values["latitude"] is None or values["longitude"] is None:
        raise ValidationError({"latitude": "Hazard coordinates are required."})
    try:
        geo.haversine_km(values["latitude"], values["longitude"], 0, 0)
    except geo.InvalidCoordinates as exc:
        raise ValidationError({"latitude": "Hazard coordinates are out of range."}) from exc
    return values


def monitored_projects():
    """Active projects whose lifecycle status is monitored (not planning)."""

    return Project.objects.filter(status__in=safety_policy.MONITORED_PROJECT_STATUSES)


def monitoring_coverage():
    projects = monitored_projects()
    total = projects.count()
    with_coordinates = projects.filter(latitude__isnull=False, longitude__isnull=False).count()
    return {
        "monitored_projects": total,
        "projects_with_coordinates": with_coordinates,
        "projects_missing_coordinates": total - with_coordinates,
    }


def _created_audit_state(alert):
    return {
        "project_id": str(alert.project_id),
        "hazard_event_id": str(alert.hazard_event_id),
        "provider": alert.hazard_event.provider,
        "hazard_type": alert.hazard_type,
        "severity": alert.severity,
        "distance_km": str(alert.distance_km),
        "rule_code": alert.rule_code,
        "policy_version": alert.policy_version,
        "recommended_action": alert.recommended_action,
    }


def _alert_audit_state(alert):
    return {
        "status": alert.status,
        "severity": alert.severity,
        "rule_code": alert.rule_code,
        "policy_version": alert.policy_version,
        "recommended_action": alert.recommended_action,
        "decision": alert.decision,
        "decision_notes_length": len(alert.decision_notes or ""),
        "resolution_notes_length": len(alert.resolution_notes or ""),
        "acknowledged_by_id": str(alert.acknowledged_by_id) if alert.acknowledged_by_id else None,
        "decided_by_id": str(alert.decided_by_id) if alert.decided_by_id else None,
        "resolved_by_id": str(alert.resolved_by_id) if alert.resolved_by_id else None,
        "hazard_withdrawn": alert.hazard_withdrawn_at is not None,
    }


def _hazard_area(hazard_or_values):
    """The authoritative warned area of a hazard, or None for point/radius."""

    if isinstance(hazard_or_values, dict):
        return hazard_or_values.get("area_polygons")
    return getattr(hazard_or_values, "area_polygons", None)


def _match_projects_for(hazard_or_values, policy, hazard_type, radius_km):
    """Project matches for either geometry mode.

    Area hazards are matched by exact containment (Phase 6B); point hazards
    keep the original radius behaviour untouched.
    """

    area = _hazard_area(hazard_or_values)
    if area:
        if policy.rules_for(hazard_type) is None:
            return []
        try:
            return geo.match_projects_in_area(monitored_projects(), polygons=area)
        except geo.InvalidGeometry:
            # Fail closed: never fall back to an approximate geometry.
            logger.warning("Safety hazard area geometry was rejected during matching.")
            return []
    radius = policy.max_radius_km(hazard_type, radius_km)
    if radius is None:
        return []
    if isinstance(hazard_or_values, dict):
        latitude, longitude = hazard_or_values["latitude"], hazard_or_values["longitude"]
    else:
        latitude, longitude = hazard_or_values.latitude, hazard_or_values.longitude
    return geo.match_projects(
        monitored_projects(),
        latitude=latitude,
        longitude=longitude,
        radius_km=radius,
    )


def _snapshot_distance(hazard, alert):
    """Re-evaluate an open alert against its immutable coordinate snapshot."""

    area = _hazard_area(hazard)
    if area:
        try:
            inside = geo.point_in_multipolygon(
                alert.project_latitude, alert.project_longitude, area
            )
        except (geo.InvalidGeometry, geo.InvalidCoordinates):
            return None
        # Inside the warned area itself, so there is no distance to a centre.
        return Decimal("0.00") if inside else None
    return geo.quantize_distance(
        geo.haversine_km(
            hazard.latitude,
            hazard.longitude,
            alert.project_latitude,
            alert.project_longitude,
        )
    )


def _evaluate_distance(policy, hazard, distance_km):
    return safety_policy.evaluate(
        policy,
        hazard_type=hazard.hazard_type,
        distance_km=distance_km,
        magnitude=hazard.magnitude,
        alert_level=hazard.alert_level,
        provider_radius_km=hazard.radius_km,
    )


def _create_alert(hazard, match, outcome):
    project = match.project
    alert = ProjectSafetyAlert(
        project=project,
        hazard_event=hazard,
        hazard_type=hazard.hazard_type,
        severity=outcome.severity,
        status=ProjectSafetyAlert.Status.NEW,
        distance_km=match.distance_km,
        project_latitude=project.latitude,
        project_longitude=project.longitude,
        rule_code=outcome.rule_code,
        policy_version=outcome.policy_version,
        recommended_action=outcome.recommended_action,
    )
    alert.full_clean(validate_unique=False, validate_constraints=False)
    # The unique (project, hazard_event) constraint is the race-safe gate.
    with transaction.atomic():
        alert.save()
    record_audit(
        actor=None,
        action="safety_alert.created",
        entity=alert,
        after=_created_audit_state(alert),
    )
    schedule_alert_notifications(alert, kind=KIND_CREATED)
    return alert


def _escalate_alert(alert, hazard, outcome, distance_km, now):
    before = _alert_audit_state(alert)
    alert.severity = outcome.severity
    alert.rule_code = outcome.rule_code
    alert.policy_version = outcome.policy_version
    alert.recommended_action = outcome.recommended_action
    alert.distance_km = distance_km
    alert.escalated_at = now
    alert.full_clean(validate_unique=False, validate_constraints=False)
    alert.save(
        update_fields=[
            "severity",
            "rule_code",
            "policy_version",
            "recommended_action",
            "distance_km",
            "escalated_at",
            "updated_at",
        ]
    )
    after = _alert_audit_state(alert)
    after["hazard_revision"] = hazard.revision
    record_audit(
        actor=None,
        action="safety_alert.escalated",
        entity=alert,
        before=before,
        after=after,
    )
    schedule_alert_notifications(alert, kind=KIND_ESCALATED)


def _withdraw_alerts(hazard, now, result):
    alerts = ProjectSafetyAlert.all_objects.select_for_update(of=("self",)).filter(
        hazard_event=hazard,
        is_active=True,
        status__in=OPEN_ALERT_STATUSES,
        hazard_withdrawn_at__isnull=True,
    )
    for alert in alerts:
        before = _alert_audit_state(alert)
        alert.hazard_withdrawn_at = now
        alert.save(update_fields=["hazard_withdrawn_at", "updated_at"])
        after = _alert_audit_state(alert)
        after["provider_status"] = hazard.provider_status
        record_audit(
            actor=None,
            action="safety_alert.hazard_withdrawn",
            entity=alert,
            before=before,
            after=after,
        )
        schedule_alert_notifications(alert, kind=KIND_WITHDRAWN)
        result.alerts_withdrawn += 1


def _evaluate_alerts(hazard, policy, now, result):
    """Escalate open alerts and create alerts for newly affected projects."""

    existing = list(
        ProjectSafetyAlert.all_objects.select_for_update(of=("self",)).filter(hazard_event=hazard)
    )
    alerted_project_ids = {alert.project_id for alert in existing}
    for alert in existing:
        if not alert.is_active or alert.status not in OPEN_ALERT_STATUSES:
            continue
        # Existing alerts are re-evaluated against their coordinate snapshot,
        # never against later edits to the project record.
        distance = _snapshot_distance(hazard, alert)
        if distance is None:
            # An area hazard whose warned area no longer covers the snapshot.
            continue
        outcome = _evaluate_distance(policy, hazard, distance)
        if outcome and safety_policy.is_higher_severity(outcome.severity, alert.severity):
            _escalate_alert(alert, hazard, outcome, distance, now)
            result.alerts_escalated += 1

    if safety_policy.is_stale(
        policy,
        hazard_type=hazard.hazard_type,
        occurred_at=hazard.occurred_at,
        provider_updated_at=hazard.provider_updated_at,
        now=now,
    ):
        return
    for match in _match_projects_for(
        hazard, policy, hazard.hazard_type, hazard.radius_km
    ):
        if match.project.pk in alerted_project_ids:
            continue
        outcome = _evaluate_distance(policy, hazard, match.distance_km)
        if outcome is None:
            continue
        _create_alert(hazard, match, outcome)
        result.alerts_created += 1


def _has_candidate_projects(values, policy):
    return bool(
        _match_projects_for(values, policy, values["hazard_type"], values["radius_km"])
    )


def _identity_candidates(event, values):
    """Provider identifiers that may already denote this logical hazard."""

    candidates = [values["provider_event_id"]]
    for alias in getattr(event, "identity_aliases", ()) or ():
        alias = str(alias).strip()[:128]
        if alias and alias not in candidates:
            candidates.append(alias)
    return candidates


def _resolve_by_alias(provider, candidates):
    """Find an existing hazard through a previously recorded identifier."""

    alias = (
        HazardEventAlias.all_objects.filter(
            provider=provider, alias_identifier__in=candidates
        )
        .select_related("hazard_event")
        .first()
    )
    return alias.hazard_event if alias is not None else None


def _record_identity_aliases(event, hazard, candidates):
    """Remember every identifier this chain has used. Never reassigns one.

    Only providers that actually issue multiple identifiers for one logical
    event write here; a provider with one stable identifier per event never
    creates a row.
    """

    if not getattr(event, "identity_aliases", ()):
        return
    for identifier in candidates:
        try:
            with transaction.atomic():
                HazardEventAlias.all_objects.get_or_create(
                    provider=hazard.provider,
                    alias_identifier=identifier,
                    defaults={"hazard_event": hazard},
                )
        except IntegrityError:
            # Another worker recorded it first; the existing row stands.
            continue


def _ingest_one(event, policy, now, result):
    values = _validated_fields(event)
    candidates = _identity_candidates(event, values)
    with transaction.atomic():
        hazard = (
            HazardEvent.all_objects.select_for_update(of=("self",))
            .filter(provider=values["provider"], provider_event_id=values["provider_event_id"])
            .first()
        )
        if hazard is None and len(candidates) > 1:
            # A later revision whose root message has aged out of the feed.
            hazard = _resolve_by_alias(values["provider"], candidates)
            if hazard is not None:
                hazard = (
                    HazardEvent.all_objects.select_for_update(of=("self",))
                    .filter(pk=hazard.pk)
                    .first()
                )
        if hazard is not None:
            # The stored identity is authoritative; a revision never renames it.
            values["provider_event_id"] = hazard.provider_event_id
        if hazard is None:
            if getattr(event, "revision_of_existing", False):
                # Fail closed: a revision of an event we have never seen must
                # not become a second hazard for the same warning chain.
                result.events_ignored += 1
                return
            if (
                values["provider_status"] != HazardEvent.ProviderStatus.ACTIVE
                or policy.rules_for(values["hazard_type"]) is None
                or not _has_candidate_projects(values, policy)
            ):
                # Only persist facts that could affect a monitored project.
                result.events_ignored += 1
                return
            hazard = HazardEvent(**values, revision=1, last_seen_at=now)
            hazard.full_clean(validate_unique=False, validate_constraints=False)
            with transaction.atomic():
                hazard.save()
            _record_identity_aliases(event, hazard, candidates)
            result.events_created += 1
            _evaluate_alerts(hazard, policy, now, result)
            return
        _record_identity_aliases(event, hazard, candidates)

        if values["provider_updated_at"] < hazard.provider_updated_at:
            # An older provider update must never overwrite newer state.
            result.stale_updates_ignored += 1
            return
        if values["provider_updated_at"] == hazard.provider_updated_at:
            hazard.last_seen_at = now
            hazard.save(update_fields=["last_seen_at", "updated_at"])
            result.events_unchanged += 1
            return

        was_active = hazard.provider_status == HazardEvent.ProviderStatus.ACTIVE
        for name, value in values.items():
            setattr(hazard, name, value)
        hazard.revision += 1
        hazard.last_seen_at = now
        hazard.full_clean(validate_unique=False, validate_constraints=False)
        hazard.save()
        result.events_updated += 1
        if hazard.provider_status == HazardEvent.ProviderStatus.ACTIVE:
            _evaluate_alerts(hazard, policy, now, result)
        elif was_active and hazard.provider_status == HazardEvent.ProviderStatus.WITHDRAWN:
            _withdraw_alerts(hazard, now, result)


_COUNTER_FIELDS = (
    "events_created",
    "events_updated",
    "events_unchanged",
    "events_ignored",
    "stale_updates_ignored",
    "alerts_created",
    "alerts_escalated",
    "alerts_withdrawn",
)


def _merge_counts(total, event_result):
    for name in _COUNTER_FIELDS:
        setattr(total, name, getattr(total, name) + getattr(event_result, name))


def ingest_hazard_events(events, *, now=None):
    """Persist provider facts and evaluate project alerts idempotently.

    Each event is processed in its own transaction, so one invalid or failing
    event never blocks the others or corrupts previously committed alerts.
    When either kill switch is off, nothing is written.
    """

    events = list(events)
    result = IngestionResult(received=len(events))
    if not safety_policy.alert_creation_enabled():
        result.enabled = False
        return result
    now = now or timezone.now()
    policy = safety_policy.load_policy()
    for event in events:
        try:
            try:
                event_result = IngestionResult(received=0)
                _ingest_one(event, policy, now, event_result)
            except IntegrityError:
                # A concurrent ingestion created the same row; the failed
                # transaction rolled back, so re-read and apply it once more.
                event_result = IngestionResult(received=0)
                _ingest_one(event, policy, now, event_result)
            _merge_counts(result, event_result)
        except (ValidationError, geo.InvalidCoordinates) as exc:
            result.invalid_skipped += 1
            error_fields = sorted(getattr(exc, "message_dict", {}) or {})
            logger.warning(
                "Invalid hazard event skipped.",
                extra={"provider": getattr(event, "provider", None), "fields": error_fields},
            )
    return result


# ---------------------------------------------------------------------------
# Human workflow
# ---------------------------------------------------------------------------


def available_actions(alert):
    """Server-calculated workflow actions for the alert's current status."""

    return list(AVAILABLE_ACTIONS_BY_STATUS.get(alert.status, ()))


def _require_manager(actor, alert):
    if actor is None or not getattr(actor, "pk", None) or not actor.is_active:
        raise ValidationError({"actor": "An active authenticated actor is required."})
    if not user_can_manage_alert(actor, alert):
        raise PermissionDenied("This user cannot manage this safety alert.")


def _locked_alert(alert_id):
    return (
        ProjectSafetyAlert.all_objects.select_for_update(of=("self",))
        .select_related("project", "hazard_event")
        .get(pk=alert_id, is_active=True)
    )


def _clean_notes(value, field_name, *, required):
    text = (value or "").strip()
    if required and not text:
        raise ValidationError({field_name: "This field is required."})
    if len(text) > MAX_NOTES_LENGTH:
        raise ValidationError(
            {field_name: f"Ensure this field has no more than {MAX_NOTES_LENGTH} characters."}
        )
    if any(ord(character) < 32 and character not in "\n\r\t" for character in text):
        raise ValidationError({field_name: "Control characters are not allowed."})
    return text


def _require_status(alert, allowed, message):
    if alert.status not in allowed:
        raise ValidationError({"status": message})


def _save_transition(alert, actor, action, before, update_fields, request):
    alert.full_clean(validate_unique=False)
    alert.save(update_fields=[*update_fields, "updated_at"])
    record_audit(
        actor=actor,
        action=action,
        entity=alert,
        before=before,
        after=_alert_audit_state(alert),
        request=request,
    )
    return alert


@transaction.atomic
def acknowledge_alert(*, alert_id, actor, request=None):
    alert = _locked_alert(alert_id)
    _require_manager(actor, alert)
    if (
        alert.status == ProjectSafetyAlert.Status.ACKNOWLEDGED
        and alert.acknowledged_by_id == actor.pk
    ):
        return alert
    _require_status(
        alert,
        {ProjectSafetyAlert.Status.NEW},
        "Only a new safety alert can be acknowledged.",
    )
    before = _alert_audit_state(alert)
    alert.status = ProjectSafetyAlert.Status.ACKNOWLEDGED
    alert.acknowledged_by = actor
    alert.acknowledged_at = timezone.now()
    return _save_transition(
        alert,
        actor,
        "safety_alert.acknowledged",
        before,
        ["status", "acknowledged_by", "acknowledged_at"],
        request,
    )


@transaction.atomic
def decide_alert_action(*, alert_id, actor, decision, notes="", request=None):
    """Record a final protective decision directly.

    Reserved for the General Manager / Super Admin. Recording a decision here
    reaches people -- it is the trigger for outbound Telegram -- so it carries
    the same authority as approving a proposal. Construction and Operations
    Managers reach this outcome through
    :mod:`apps.safety.proposals`, by proposing an action for approval.
    """

    alert = _locked_alert(alert_id)
    _require_manager(actor, alert)
    if not user_can_approve_safety(actor):
        raise PermissionDenied(
            "Recording a final safety decision requires General Manager approval authority."
        )
    if decision not in SAFETY_ACTION_VALUES:
        raise ValidationError({"decision": "Select a supported safety action."})
    notes = _clean_notes(
        notes,
        "decision_notes",
        required=decision == ProjectSafetyAlert.Action.OTHER,
    )
    _require_status(
        alert,
        {ProjectSafetyAlert.Status.ACKNOWLEDGED, ProjectSafetyAlert.Status.ACTIONED},
        "A decision requires an acknowledged or actioned safety alert.",
    )
    if (
        alert.status == ProjectSafetyAlert.Status.ACTIONED
        and alert.decision == decision
        and alert.decision_notes == notes
    ):
        return alert
    before = _alert_audit_state(alert)
    alert.status = ProjectSafetyAlert.Status.ACTIONED
    alert.decision = decision
    alert.decision_notes = notes
    alert.decided_by = actor
    alert.decided_at = timezone.now()
    alert = _save_transition(
        alert,
        actor,
        "safety_alert.action_decided",
        before,
        ["status", "decision", "decision_notes", "decided_by", "decided_at"],
        request,
    )
    # The only Telegram trigger in the platform: a human recorded a decision.
    # Scheduled post-commit, so it cannot roll this transition back.
    schedule_decision_delivery(alert)
    return alert


@transaction.atomic
def dismiss_alert(*, alert_id, actor, reason, request=None):
    alert = _locked_alert(alert_id)
    _require_manager(actor, alert)
    reason = _clean_notes(reason, "reason", required=True)
    _require_status(
        alert,
        {ProjectSafetyAlert.Status.NEW, ProjectSafetyAlert.Status.ACKNOWLEDGED},
        "Only a new or acknowledged safety alert can be dismissed.",
    )
    before = _alert_audit_state(alert)
    alert.status = ProjectSafetyAlert.Status.DISMISSED
    alert.resolution_notes = reason
    alert.resolved_by = actor
    alert.resolved_at = timezone.now()
    return _save_transition(
        alert,
        actor,
        "safety_alert.dismissed",
        before,
        ["status", "resolution_notes", "resolved_by", "resolved_at"],
        request,
    )


@transaction.atomic
def close_alert(*, alert_id, actor, notes="", request=None):
    alert = _locked_alert(alert_id)
    _require_manager(actor, alert)
    notes = _clean_notes(notes, "notes", required=False)
    _require_status(
        alert,
        {ProjectSafetyAlert.Status.ACTIONED},
        "Only an actioned safety alert can be closed.",
    )
    before = _alert_audit_state(alert)
    alert.status = ProjectSafetyAlert.Status.CLOSED
    alert.resolution_notes = notes
    alert.resolved_by = actor
    alert.resolved_at = timezone.now()
    return _save_transition(
        alert,
        actor,
        "safety_alert.closed",
        before,
        ["status", "resolution_notes", "resolved_by", "resolved_at"],
        request,
    )
