import copy
import logging
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError

from apps.common.models import SystemSetting
from apps.safety import policy
from apps.safety.tests.helpers import NOW, set_setting


def _evaluate(hazard_type="earthquake", distance_km=10, **kwargs):
    return policy.evaluate(
        policy.default_policy(),
        hazard_type=hazard_type,
        distance_km=distance_km,
        **kwargs,
    )


def test_default_policy_passes_its_own_validation():
    policy.validate_policy_override(policy.DEFAULT_POLICY)


def test_monitored_statuses_exclude_planning():
    assert policy.MONITORED_PROJECT_STATUSES == ("in_progress", "operational")


@pytest.mark.parametrize(
    "magnitude,distance,expected",
    [
        ("6.7", 200, ("critical", "earthquake.m6_5_r250", "suspend_outdoor_work")),
        ("6.7", 90, ("critical", "earthquake.m6_5_r250", "suspend_outdoor_work")),
        ("6.0", 90, ("high", "earthquake.m5_5_r100", "suspend_outdoor_work")),
        ("5.0", 40, ("medium", "earthquake.m4_5_r50", "inspect_site")),
        ("6.7", 260, None),
        ("5.0", 60, None),
        ("4.4", 1, None),
    ],
)
def test_earthquake_tiers(magnitude, distance, expected):
    outcome = _evaluate(distance_km=distance, magnitude=magnitude)
    if expected is None:
        assert outcome is None
    else:
        assert (outcome.severity, outcome.rule_code, outcome.recommended_action) == expected
        assert outcome.policy_version == 0


def test_highest_severity_wins_when_several_tiers_match():
    outcome = _evaluate(distance_km=30, magnitude="7.0")
    assert outcome.severity == "critical"


def test_alert_level_tiers_and_green_is_ignored():
    assert _evaluate("flood", 40, alert_level="red").severity == "critical"
    assert _evaluate("flood", 40, alert_level="orange").severity == "high"
    assert _evaluate("flood", 40, alert_level="green") is None
    assert _evaluate("flood", 40, alert_level=None) is None


def test_missing_magnitude_unknown_hazard_and_bad_distance_return_none():
    assert _evaluate(magnitude=None) is None
    assert _evaluate("extreme_heat", 1, magnitude="9") is None
    assert _evaluate(distance_km=-1, magnitude="7") is None
    assert _evaluate(distance_km=float("nan"), magnitude="7") is None


def test_provider_radius_extends_but_is_capped():
    assert _evaluate("flood", 70, alert_level="orange") is None
    assert _evaluate("flood", 70, alert_level="orange", provider_radius_km=80).severity == "high"
    assert _evaluate("flood", 1500, alert_level="red", provider_radius_km=5000) is None


def test_evaluation_is_deterministic():
    first = _evaluate(distance_km=45, magnitude="6.9")
    assert all(_evaluate(distance_km=45, magnitude="6.9") == first for _ in range(20))


def _valid_override():
    return {
        "hazards": {
            "earthquake": {
                "max_event_age_hours": 12,
                "tiers": [
                    {"min_magnitude": 5.0, "radius_km": 80, "severity": "high", "recommended_action": "inspect_site"}
                ],
            }
        }
    }


def _bad(mutator):
    document = _valid_override()
    mutator(document)
    return document


def _tier(document):
    return document["hazards"]["earthquake"]["tiers"][0]


@pytest.mark.parametrize(
    "document",
    [
        [],
        "policy",
        {"unexpected": {}},
        {"hazards": []},
        {"hazards": {"tsunami": {}}},
        {"hazards": {"earthquake": []}},
        _bad(lambda d: d["hazards"]["earthquake"].update(extra=1)),
        _bad(lambda d: d["hazards"]["earthquake"].update(max_event_age_hours=0)),
        _bad(lambda d: d["hazards"]["earthquake"].update(max_event_age_hours=True)),
        _bad(lambda d: d["hazards"]["earthquake"].update(max_event_age_hours=721)),
        _bad(lambda d: d["hazards"]["earthquake"].update(tiers=[])),
        _bad(lambda d: d["hazards"]["earthquake"].update(tiers=[_tier(d)] * 11)),
        _bad(lambda d: d["hazards"]["earthquake"].update(tiers=["tier"])),
        _bad(lambda d: _tier(d).pop("severity")),
        _bad(lambda d: _tier(d).update(min_alert_level="red")),
        _bad(lambda d: _tier(d).update(severity="extreme")),
        _bad(lambda d: _tier(d).update(recommended_action="other")),
        _bad(lambda d: _tier(d).update(recommended_action="evacuate")),
        _bad(lambda d: _tier(d).update(radius_km=0)),
        _bad(lambda d: _tier(d).update(radius_km=1001)),
        _bad(lambda d: _tier(d).update(radius_km="50")),
        _bad(lambda d: _tier(d).update(radius_km=True)),
        _bad(lambda d: _tier(d).update(radius_km=float("inf"))),
        _bad(lambda d: _tier(d).update(min_magnitude=11)),
        {"hazards": {"flood": {"tiers": [{"min_alert_level": "purple", "radius_km": 10, "severity": "high", "recommended_action": "monitor"}]}}},
    ],
)
def test_invalid_overrides_are_rejected(document):
    with pytest.raises(ValidationError):
        policy.validate_policy_override(document)


def test_valid_override_and_boolean_setting_validation():
    policy.validate_policy_override(_valid_override())
    policy.validate_policy_override({})
    policy.validate_safety_setting("safety.hazardPolicy", _valid_override())
    policy.validate_safety_setting("safety.externalAlerts", False)
    policy.validate_safety_setting("unrelated.setting", "anything")
    with pytest.raises(ValidationError):
        policy.validate_safety_setting("safety.externalAlerts", "true")
    with pytest.raises(ValidationError):
        policy.validate_safety_setting("notify.safetyAlerts", 1)


@pytest.mark.django_db
def test_load_policy_defaults_when_absent_or_empty():
    SystemSetting.objects.filter(key=policy.POLICY_SETTING_KEY).delete()
    assert policy.load_policy() == policy.default_policy()
    set_setting(policy.POLICY_SETTING_KEY, {})
    assert policy.load_policy().version == 0


@pytest.mark.django_db
def test_load_policy_applies_valid_override_with_setting_version():
    setting = set_setting(policy.POLICY_SETTING_KEY, _valid_override())
    SystemSetting.objects.filter(pk=setting.pk).update(version=7)

    loaded = policy.load_policy()

    assert loaded.version == 7
    rules = loaded.rules_for("earthquake")
    assert rules.max_event_age_hours == 12
    assert len(rules.tiers) == 1
    assert loaded.rules_for("flood") == policy.default_policy().rules_for("flood")
    outcome = policy.evaluate(loaded, hazard_type="earthquake", distance_km=70, magnitude="5.2")
    assert (outcome.severity, outcome.policy_version) == ("high", 7)


@pytest.mark.django_db
def test_load_policy_falls_back_safely_and_logs_without_values(caplog):
    marker = "SECRET-LOOKING-VALUE-123"
    set_setting(policy.POLICY_SETTING_KEY, {"hazards": {"earthquake": {"tiers": marker}}})

    with caplog.at_level(logging.ERROR, logger="apps.safety.policy"):
        loaded = policy.load_policy()

    assert loaded == policy.default_policy()
    assert "Invalid safety policy override" in caplog.text
    assert marker not in caplog.text


@pytest.mark.django_db
@pytest.mark.parametrize(
    "env_enabled,setting_value,expected",
    [(False, False, False), (True, False, False), (False, True, False), (True, True, True), (True, "yes", False)],
)
def test_alert_creation_requires_both_kill_switches(settings, env_enabled, setting_value, expected):
    settings.SAFETY_ALERTS_ENABLED = env_enabled
    set_setting(policy.ALERTS_SETTING_KEY, setting_value)
    assert policy.alert_creation_enabled() is expected


@pytest.mark.django_db
def test_alert_creation_disabled_when_setting_missing(settings):
    settings.SAFETY_ALERTS_ENABLED = True
    SystemSetting.objects.filter(key=policy.ALERTS_SETTING_KEY).delete()
    assert policy.alert_creation_enabled() is False


def test_is_stale_uses_hazard_age_limit():
    default = policy.default_policy()
    assert not policy.is_stale(default, hazard_type="earthquake", occurred_at=NOW - timedelta(hours=5), now=NOW)
    assert policy.is_stale(default, hazard_type="earthquake", occurred_at=NOW - timedelta(hours=7), now=NOW)
    # A hazard type with no configured rules is always stale. `extreme_cold`
    # is the example now that `extreme_heat` carries an official-warning rule.
    assert policy.is_stale(default, hazard_type="extreme_cold", occurred_at=NOW, now=NOW)


def test_default_policy_document_is_not_mutated_by_overrides():
    snapshot = copy.deepcopy(policy.DEFAULT_POLICY)
    policy._merged_policy_document(_valid_override())
    assert policy.DEFAULT_POLICY == snapshot
