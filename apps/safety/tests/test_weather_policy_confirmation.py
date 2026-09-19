"""Phase 6C.2 — confirmation of the approved weather policy defaults.

No production behaviour changed in this phase. These tests pin the approved
decisions so a later change cannot quietly introduce a measurement threshold,
an autonomous action, or a different recommendation.
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.safety import policy as safety_policy
from apps.safety.models import ProjectSafetyAlert
from apps.safety.services import ingest_hazard_events
from apps.safety.tests.helpers import (
    NOW,
    assign_construction_manager,
    enable_alerts,
    make_project,
    make_user,
    set_setting,
)
from apps.safety.tests.test_provider_mhews import cap
from apps.users.models import Role


pytestmark = pytest.mark.django_db

WEATHER_HAZARDS = ("extreme_heat", "dust_storm")


@pytest.fixture
def world(settings, super_admin_user):
    enable_alerts(settings)
    settings.SAFETY_WEATHER_ENABLED = True
    cm = make_user(Role.CONSTRUCTION_MANAGER, "cm")
    project = make_project(
        super_admin_user,
        name="Inside warned area",
        latitude=Decimal("35.500000"),
        longitude=Decimal("39.500000"),
    )
    assign_construction_manager(project, cm, super_admin_user)
    return {"admin": super_admin_user, "cm": cm, "project": project}


def ingest(**kwargs):
    from apps.safety.providers import mhews

    events = mhews.normalize_documents([mhews.parse_xml(cap(**kwargs))]).events
    return ingest_hazard_events(events, now=NOW)


# ---------------------------------------------------------------------------
# Criterion: official warning severity only, never a measurement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("hazard_type", WEATHER_HAZARDS)
def test_weather_hazards_use_the_alert_level_criterion_only(hazard_type):
    assert safety_policy.CRITERION_BY_HAZARD[hazard_type] == "min_alert_level"
    rules = safety_policy.load_policy().rules_for(hazard_type)
    assert {tier.criterion for tier in rules.tiers} == {"min_alert_level"}


@pytest.mark.parametrize("hazard_type", WEATHER_HAZARDS)
def test_a_measurement_tier_is_rejected_by_the_policy_validator(hazard_type):
    """Temperature, visibility, wind and the like are not expressible."""

    for measurement in ("min_temperature", "min_wind_speed", "max_visibility_km", "min_pm10"):
        with pytest.raises(ValidationError):
            safety_policy.validate_safety_setting(
                safety_policy.POLICY_SETTING_KEY,
                {
                    "hazards": {
                        hazard_type: {
                            "tiers": [
                                {
                                    measurement: 45,
                                    "radius_km": 25,
                                    "severity": "high",
                                    "recommended_action": "monitor",
                                }
                            ]
                        }
                    }
                },
            )


# ---------------------------------------------------------------------------
# Red and orange behaviour, and that neither is autonomous
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("severity", ["Extreme", "Severe"])
def test_red_produces_a_critical_recommendation_and_nothing_else(world, severity):
    ingest(event_code="OET-098", severity=severity)
    alert = ProjectSafetyAlert.objects.get()
    assert alert.hazard_type == "extreme_heat"
    assert alert.severity == "critical"
    assert alert.recommended_action == "suspend_outdoor_work"
    # A recommendation, not an action: nothing was decided or actioned, and the
    # project itself is untouched.
    assert alert.status == ProjectSafetyAlert.Status.NEW
    assert alert.decision is None
    assert alert.decided_by_id is None
    assert alert.decided_at is None
    assert alert.acknowledged_at is None
    world["project"].refresh_from_db()
    assert world["project"].status == "in_progress"


def test_orange_produces_a_high_recommendation_and_nothing_else(world):
    ingest(event_code="OET-170", severity="Moderate")
    alert = ProjectSafetyAlert.objects.get()
    assert alert.hazard_type == "dust_storm"
    assert alert.severity == "high"
    assert alert.recommended_action == "increase_precautions"
    assert alert.status == ProjectSafetyAlert.Status.NEW
    assert alert.decision is None
    world["project"].refresh_from_db()
    assert world["project"].status == "in_progress"


def test_unknown_severity_produces_no_alert(world):
    for severity in ("Unknown", "", "Catastrophic"):
        ingest(event_code="OET-098", severity=severity)
    assert ProjectSafetyAlert.objects.count() == 0


def test_green_matches_no_default_tier(world):
    ingest(event_code="OET-170", severity="Minor")
    assert ProjectSafetyAlert.objects.count() == 0


# ---------------------------------------------------------------------------
# Operator override through the existing mechanism
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("hazard_type", WEATHER_HAZARDS)
def test_operators_can_override_weather_policy_through_the_existing_setting(hazard_type):
    override = {
        "hazards": {
            hazard_type: {
                "max_event_age_hours": 24,
                "tiers": [
                    {
                        "min_alert_level": "red",
                        "radius_km": 25,
                        "severity": "high",
                        "recommended_action": "modify_working_hours",
                    }
                ],
            }
        }
    }
    safety_policy.validate_safety_setting(safety_policy.POLICY_SETTING_KEY, override)
    set_setting(safety_policy.POLICY_SETTING_KEY, override)

    rules = safety_policy.load_policy().rules_for(hazard_type)
    assert rules.max_event_age_hours == 24
    assert [tier.recommended_action for tier in rules.tiers] == ["modify_working_hours"]
    # The shipped default is untouched by an override.
    assert (
        safety_policy.DEFAULT_POLICY["hazards"][hazard_type]["tiers"][0]["recommended_action"]
        == "suspend_outdoor_work"
    )


def test_an_override_for_one_weather_hazard_leaves_the_others_alone():
    set_setting(
        safety_policy.POLICY_SETTING_KEY,
        {
            "hazards": {
                "extreme_heat": {
                    "tiers": [
                        {
                            "min_alert_level": "red",
                            "radius_km": 25,
                            "severity": "medium",
                            "recommended_action": "monitor",
                        }
                    ]
                }
            }
        },
    )
    policy = safety_policy.load_policy()
    assert [tier.severity for tier in policy.rules_for("extreme_heat").tiers] == ["medium"]
    assert [tier.severity for tier in policy.rules_for("dust_storm").tiers] == [
        "critical",
        "high",
    ]
    assert [tier.severity for tier in policy.rules_for("flood").tiers] == ["critical", "high"]


# ---------------------------------------------------------------------------
# Existing hazards must be exactly as they were
# ---------------------------------------------------------------------------


def test_pre_existing_hazard_policies_are_unchanged():
    expected = {
        "earthquake": (6, [(6.5, "critical", "suspend_outdoor_work"),
                           (5.5, "high", "suspend_outdoor_work"),
                           (4.5, "medium", "inspect_site")]),
        "flood": (72, [("red", "critical", "suspend_outdoor_work"),
                       ("orange", "high", "increase_precautions")]),
        "tropical_cyclone": (72, [("red", "critical", "suspend_outdoor_work"),
                                  ("orange", "high", "delay_shift")]),
        "volcano": (72, [("red", "critical", "suspend_outdoor_work"),
                         ("orange", "high", "increase_precautions")]),
        "wildfire": (72, [("red", "critical", "suspend_outdoor_work"),
                          ("orange", "high", "increase_precautions")]),
    }
    for hazard_type, (age, tiers) in expected.items():
        rules = safety_policy.DEFAULT_POLICY["hazards"][hazard_type]
        assert rules["max_event_age_hours"] == age, hazard_type
        criterion = safety_policy.CRITERION_BY_HAZARD[hazard_type]
        actual = [
            (tier[criterion], tier["severity"], tier["recommended_action"])
            for tier in rules["tiers"]
        ]
        assert actual == tiers, hazard_type


def test_severity_architecture_is_unchanged():
    from apps.safety.models import HAZARD_ALERT_LEVEL_VALUES, SAFETY_SEVERITY_VALUES

    assert HAZARD_ALERT_LEVEL_VALUES == ("green", "orange", "red")
    assert SAFETY_SEVERITY_VALUES == ("low", "medium", "high", "critical")
    assert safety_policy.ALERT_LEVEL_RANK == {"green": 0, "orange": 1, "red": 2}
