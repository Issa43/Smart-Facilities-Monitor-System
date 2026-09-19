"""Deterministic safety policy for external hazards.

All hazard thresholds live here. ``DEFAULT_POLICY`` is an illustrative
starting policy, not an approved HSE/business standard; operators replace it
per hazard through the validated ``safety.hazardPolicy`` SystemSetting.

Alert creation additionally requires both kill switches:
``settings.SAFETY_ALERTS_ENABLED`` and the ``safety.externalAlerts`` setting.
Both default to off.
"""

import copy
import logging
import math
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.common.models import SystemSetting
from apps.notifications.services import setting_enabled

from .models import (
    HAZARD_ALERT_LEVEL_VALUES,
    SAFETY_SEVERITY_VALUES,
    SYSTEM_RECOMMENDABLE_ACTION_VALUES,
)


logger = logging.getLogger(__name__)

POLICY_SETTING_KEY = "safety.hazardPolicy"
ALERTS_SETTING_KEY = "safety.externalAlerts"
NOTIFY_SETTING_KEY = "notify.safetyAlerts"
BOOLEAN_SETTING_KEYS = frozenset({ALERTS_SETTING_KEY, NOTIFY_SETTING_KEY})

# D4: planning projects are intentionally not monitored.
MONITORED_PROJECT_STATUSES = ("in_progress", "operational")

MAX_POLICY_RADIUS_KM = 1000.0
MAX_TIERS_PER_HAZARD = 10
MIN_EVENT_AGE_HOURS = 1
MAX_EVENT_AGE_HOURS = 720

SEVERITY_RANK = {severity: rank for rank, severity in enumerate(SAFETY_SEVERITY_VALUES)}
ALERT_LEVEL_RANK = {level: rank for rank, level in enumerate(HAZARD_ALERT_LEVEL_VALUES)}

# Hazards that remain active over time; their age follows provider revisions.
ONGOING_HAZARD_TYPES = frozenset({"tropical_cyclone", "flood", "volcano", "wildfire"})

# Each supported hazard is evaluated on exactly one criterion.
#
# Official weather warnings (extreme heat, dust storms) are evaluated on
# ``min_alert_level`` like every other non-earthquake hazard: the criterion
# reads the normalized severity of an official warning that an authority has
# already issued. The platform never measures temperature, visibility, wind or
# rainfall itself, and no meteorological threshold exists anywhere in this
# module.
CRITERION_BY_HAZARD = {
    "earthquake": "min_magnitude",
    "tropical_cyclone": "min_alert_level",
    "flood": "min_alert_level",
    "volcano": "min_alert_level",
    "wildfire": "min_alert_level",
    "extreme_heat": "min_alert_level",
    "dust_storm": "min_alert_level",
}

DEFAULT_POLICY = {
    "hazards": {
        "earthquake": {
            "max_event_age_hours": 6,
            "tiers": [
                {"min_magnitude": 6.5, "radius_km": 250, "severity": "critical", "recommended_action": "suspend_outdoor_work"},
                {"min_magnitude": 5.5, "radius_km": 100, "severity": "high", "recommended_action": "suspend_outdoor_work"},
                {"min_magnitude": 4.5, "radius_km": 50, "severity": "medium", "recommended_action": "inspect_site"},
            ],
        },
        "tropical_cyclone": {
            "max_event_age_hours": 72,
            "tiers": [
                {"min_alert_level": "red", "radius_km": 500, "severity": "critical", "recommended_action": "suspend_outdoor_work"},
                {"min_alert_level": "orange", "radius_km": 300, "severity": "high", "recommended_action": "delay_shift"},
            ],
        },
        "flood": {
            "max_event_age_hours": 72,
            "tiers": [
                {"min_alert_level": "red", "radius_km": 100, "severity": "critical", "recommended_action": "suspend_outdoor_work"},
                {"min_alert_level": "orange", "radius_km": 50, "severity": "high", "recommended_action": "increase_precautions"},
            ],
        },
        "volcano": {
            "max_event_age_hours": 72,
            "tiers": [
                {"min_alert_level": "red", "radius_km": 100, "severity": "critical", "recommended_action": "suspend_outdoor_work"},
                {"min_alert_level": "orange", "radius_km": 50, "severity": "high", "recommended_action": "increase_precautions"},
            ],
        },
        "wildfire": {
            "max_event_age_hours": 72,
            "tiers": [
                {"min_alert_level": "red", "radius_km": 100, "severity": "critical", "recommended_action": "suspend_outdoor_work"},
                {"min_alert_level": "orange", "radius_km": 50, "severity": "high", "recommended_action": "increase_precautions"},
            ],
        },
        # Official weather warnings. These arrive with an authoritative warned
        # area, so containment decides which projects are affected and the
        # radius below is never consulted; it is present because every tier
        # carries one. As with every other entry here, the severity and action
        # are illustrative defaults, not an approved HSE standard - operators
        # replace them through `safety.hazardPolicy`.
        "extreme_heat": {
            "max_event_age_hours": 72,
            "tiers": [
                {"min_alert_level": "red", "radius_km": 100, "severity": "critical", "recommended_action": "suspend_outdoor_work"},
                {"min_alert_level": "orange", "radius_km": 50, "severity": "high", "recommended_action": "increase_precautions"},
            ],
        },
        "dust_storm": {
            "max_event_age_hours": 72,
            "tiers": [
                {"min_alert_level": "red", "radius_km": 100, "severity": "critical", "recommended_action": "suspend_outdoor_work"},
                {"min_alert_level": "orange", "radius_km": 50, "severity": "high", "recommended_action": "increase_precautions"},
            ],
        },
    }
}


@dataclass(frozen=True)
class PolicyTier:
    criterion: str
    threshold: object
    radius_km: float
    severity: str
    recommended_action: str

    @property
    def rule_code(self):
        if self.criterion == "min_magnitude":
            value = f"m{self.threshold:g}".replace(".", "_")
        else:
            value = str(self.threshold)
        return f"{value}_r{self.radius_km:g}".replace(".", "_")


@dataclass(frozen=True)
class HazardRules:
    hazard_type: str
    max_event_age_hours: int
    tiers: tuple

    @property
    def max_radius_km(self):
        return max(tier.radius_km for tier in self.tiers)


@dataclass(frozen=True)
class SafetyPolicy:
    version: int
    hazards: dict

    def rules_for(self, hazard_type):
        return self.hazards.get(hazard_type)

    def max_radius_km(self, hazard_type, provider_radius_km=None):
        rules = self.rules_for(hazard_type)
        if rules is None:
            return None
        return effective_radius_km(rules.max_radius_km, provider_radius_km)


@dataclass(frozen=True)
class PolicyOutcome:
    severity: str
    rule_code: str
    recommended_action: str
    policy_version: int


def _is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _validate_tier(hazard_type, index, tier, errors):
    path = f"hazards.{hazard_type}.tiers[{index}]"
    criterion = CRITERION_BY_HAZARD[hazard_type]
    if not isinstance(tier, dict):
        errors.append(f"{path} must be an object.")
        return
    expected = {criterion, "radius_km", "severity", "recommended_action"}
    unknown = sorted(set(tier) - expected)
    missing = sorted(expected - set(tier))
    if unknown:
        errors.append(f"{path} has unsupported keys: {', '.join(unknown)}.")
    if missing:
        errors.append(f"{path} is missing keys: {', '.join(missing)}.")
    if unknown or missing:
        return
    threshold = tier[criterion]
    if criterion == "min_magnitude":
        if not _is_number(threshold) or not 0 <= threshold <= 10:
            errors.append(f"{path}.min_magnitude must be a number from 0 to 10.")
    elif threshold not in HAZARD_ALERT_LEVEL_VALUES:
        errors.append(f"{path}.min_alert_level must be one of green, orange, red.")
    radius = tier["radius_km"]
    if not _is_number(radius) or not 0 < radius <= MAX_POLICY_RADIUS_KM:
        errors.append(
            f"{path}.radius_km must be greater than 0 and at most {MAX_POLICY_RADIUS_KM:g}."
        )
    if tier["severity"] not in SAFETY_SEVERITY_VALUES:
        errors.append(f"{path}.severity is not a supported severity.")
    if tier["recommended_action"] not in SYSTEM_RECOMMENDABLE_ACTION_VALUES:
        errors.append(f"{path}.recommended_action is not a supported recommendation.")


def _validate_hazard(hazard_type, rules, errors):
    path = f"hazards.{hazard_type}"
    if not isinstance(rules, dict):
        errors.append(f"{path} must be an object.")
        return
    unknown = sorted(set(rules) - {"max_event_age_hours", "tiers"})
    if unknown:
        errors.append(f"{path} has unsupported keys: {', '.join(unknown)}.")
    if "max_event_age_hours" in rules:
        age = rules["max_event_age_hours"]
        if (
            not isinstance(age, int)
            or isinstance(age, bool)
            or not MIN_EVENT_AGE_HOURS <= age <= MAX_EVENT_AGE_HOURS
        ):
            errors.append(
                f"{path}.max_event_age_hours must be an integer from "
                f"{MIN_EVENT_AGE_HOURS} to {MAX_EVENT_AGE_HOURS}."
            )
    if "tiers" in rules:
        tiers = rules["tiers"]
        if not isinstance(tiers, list) or not 1 <= len(tiers) <= MAX_TIERS_PER_HAZARD:
            errors.append(
                f"{path}.tiers must be a list of 1 to {MAX_TIERS_PER_HAZARD} tiers."
            )
            return
        for index, tier in enumerate(tiers):
            _validate_tier(hazard_type, index, tier, errors)


def validate_policy_override(value):
    """Validate a ``safety.hazardPolicy`` override; raise ValidationError."""

    errors = []
    if not isinstance(value, dict):
        raise ValidationError(["The safety policy must be an object."])
    unknown = sorted(set(value) - {"hazards"})
    if unknown:
        errors.append(f"Unsupported policy keys: {', '.join(unknown)}.")
    hazards = value.get("hazards", {})
    if not isinstance(hazards, dict):
        errors.append("hazards must be an object.")
    else:
        for hazard_type, rules in hazards.items():
            if hazard_type not in CRITERION_BY_HAZARD:
                errors.append(f"hazards.{hazard_type} is not a supported hazard type.")
                continue
            _validate_hazard(hazard_type, rules, errors)
    if errors:
        raise ValidationError(errors)


def validate_safety_setting(key, value):
    """Validate a safety-owned SystemSetting value before it is saved."""

    if key == POLICY_SETTING_KEY:
        validate_policy_override(value)
    elif key in BOOLEAN_SETTING_KEYS and not isinstance(value, bool):
        raise ValidationError([f"{key} must be a boolean."])


def _merged_policy_document(override):
    document = copy.deepcopy(DEFAULT_POLICY)
    for hazard_type, rules in override.get("hazards", {}).items():
        document["hazards"][hazard_type].update(copy.deepcopy(rules))
    return document


def _build_policy(document, version):
    hazards = {}
    for hazard_type, rules in document["hazards"].items():
        criterion = CRITERION_BY_HAZARD[hazard_type]
        tiers = tuple(
            PolicyTier(
                criterion=criterion,
                threshold=tier[criterion],
                radius_km=float(tier["radius_km"]),
                severity=tier["severity"],
                recommended_action=tier["recommended_action"],
            )
            for tier in rules["tiers"]
        )
        hazards[hazard_type] = HazardRules(
            hazard_type=hazard_type,
            max_event_age_hours=int(rules["max_event_age_hours"]),
            tiers=tiers,
        )
    return SafetyPolicy(version=version, hazards=hazards)


def default_policy():
    return _build_policy(DEFAULT_POLICY, 0)


def load_policy():
    """Return the effective policy, falling back to defaults on bad config.

    The policy version is the SystemSetting version when a non-empty valid
    override is active, otherwise 0 (built-in defaults).
    """

    setting = SystemSetting.objects.filter(key=POLICY_SETTING_KEY).only("value", "version").first()
    if setting is None or setting.value in ({}, None):
        return default_policy()
    try:
        validate_policy_override(setting.value)
    except ValidationError as exc:
        # Log only the number of problems, never the configured values.
        logger.error(
            "Invalid safety policy override ignored; built-in defaults are in effect.",
            extra={"setting_key": POLICY_SETTING_KEY, "error_count": len(exc.messages)},
        )
        return default_policy()
    return _build_policy(_merged_policy_document(setting.value), setting.version)


def alert_creation_enabled():
    """Both kill switches must be on before any alert may be created."""

    return bool(settings.SAFETY_ALERTS_ENABLED) and setting_enabled(
        ALERTS_SETTING_KEY,
        default=False,
    )


def effective_radius_km(policy_radius_km, provider_radius_km=None):
    radius = float(policy_radius_km)
    if provider_radius_km is not None:
        radius = max(radius, float(provider_radius_km))
    return min(radius, MAX_POLICY_RADIUS_KM)


def _criterion_met(tier, *, magnitude, alert_level):
    if tier.criterion == "min_magnitude":
        return magnitude is not None and float(magnitude) >= float(tier.threshold)
    return (
        alert_level in ALERT_LEVEL_RANK
        and ALERT_LEVEL_RANK[alert_level] >= ALERT_LEVEL_RANK[tier.threshold]
    )


def _tier_sort_key(tier):
    threshold = (
        float(tier.threshold)
        if tier.criterion == "min_magnitude"
        else ALERT_LEVEL_RANK[tier.threshold]
    )
    return (-SEVERITY_RANK[tier.severity], -threshold, tier.radius_km, tier.recommended_action)


def evaluate(policy, *, hazard_type, distance_km, magnitude=None, alert_level=None, provider_radius_km=None):
    """Return the highest-severity matching outcome, or None.

    Ties are broken deterministically by stricter threshold, smaller radius,
    then action code, so the same inputs always produce the same outcome.
    """

    rules = policy.rules_for(hazard_type)
    if rules is None or distance_km is None:
        return None
    distance = float(distance_km)
    if not math.isfinite(distance) or distance < 0:
        return None
    for tier in sorted(rules.tiers, key=_tier_sort_key):
        if not _criterion_met(tier, magnitude=magnitude, alert_level=alert_level):
            continue
        if distance <= effective_radius_km(tier.radius_km, provider_radius_km):
            return PolicyOutcome(
                severity=tier.severity,
                rule_code=f"{hazard_type}.{tier.rule_code}",
                recommended_action=tier.recommended_action,
                policy_version=policy.version,
            )
    return None


def staleness_reference(*, hazard_type, occurred_at, provider_updated_at=None):
    """The timestamp that event age is measured from.

    Ongoing hazards (cyclones, floods, volcanoes, wildfires) can stay active for
    weeks, so their age is measured from the latest provider activity: the
    later of ``occurred_at`` and the provider revision time. Earthquakes are
    instantaneous; later provider revisions (for example a USGS review) do not
    make an old earthquake current, so their age is measured from
    ``occurred_at`` only.
    """

    if hazard_type in ONGOING_HAZARD_TYPES and provider_updated_at is not None:
        return max(occurred_at, provider_updated_at)
    return occurred_at


def is_stale(policy, *, hazard_type, occurred_at, now, provider_updated_at=None):
    """True when an event is too old to create a new alert.

    Uses the hazard's existing ``max_event_age_hours``; no separate recency
    threshold exists. An old, unchanged event is stale; an ongoing hazard whose
    provider revision falls within that same window is not.
    """

    rules = policy.rules_for(hazard_type)
    if rules is None:
        return True
    reference = staleness_reference(
        hazard_type=hazard_type,
        occurred_at=occurred_at,
        provider_updated_at=provider_updated_at,
    )
    return reference < now - timedelta(hours=rules.max_event_age_hours)


def is_higher_severity(candidate, current):
    return SEVERITY_RANK[candidate] > SEVERITY_RANK[current]
