"""MHEWS provider registration and the dust-storm hazard type (Phase 6C).

Phase 6C registers taxonomy only. There is deliberately no MHEWS adapter, no
polling and no policy: every hazard type added here stays inert until the
severity mapping and HSE thresholds are authorized. These tests pin both
halves — that the taxonomy is accepted, and that it cannot yet raise an alert.
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.safety import policy as safety_policy
from apps.safety.models import (
    HAZARD_PROVIDER_VALUES,
    HAZARD_TYPE_VALUES,
    SOURCE_URL_ALLOWED_HOSTS,
    HazardEvent,
    validate_source_url,
)


pytestmark = pytest.mark.django_db

MHEWS_SOURCE = "https://climweb.med.gov.sy/api/cap/a3787ae0-4195-41fd-8fff-65a69d596150.xml"


def hazard(**overrides):
    values = {
        "provider": "mhews",
        "provider_event_id": "urn:oid:2.49.0.1.760.1.2026.8.29.16.19.0",
        "hazard_type": "dust_storm",
        "title": "Dust storm warning",
        "latitude": Decimal("35.500000"),
        "longitude": Decimal("39.000000"),
        "occurred_at": timezone.now(),
        "provider_updated_at": timezone.now(),
        "last_seen_at": timezone.now(),
    }
    values.update(overrides)
    return HazardEvent(**values)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_mhews_provider_and_dust_storm_are_registered():
    assert "mhews" in HAZARD_PROVIDER_VALUES
    assert "dust_storm" in HAZARD_TYPE_VALUES
    assert HazardEvent.Provider.MHEWS == "mhews"
    assert HazardEvent.HazardType.DUST_STORM == "dust_storm"


def test_no_synonymous_dust_or_sand_values_were_added():
    for synonym in ("dust", "sandstorm", "sand_storm", "duststorm", "sand"):
        assert synonym not in HAZARD_TYPE_VALUES


def test_existing_providers_and_hazard_types_are_untouched():
    assert HAZARD_PROVIDER_VALUES[:2] == ("usgs", "gdacs")
    for existing in (
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
    ):
        assert existing in HAZARD_TYPE_VALUES


def test_database_accepts_an_mhews_dust_storm_row():
    event = hazard()
    event.full_clean(validate_unique=False, validate_constraints=False)
    event.save()
    assert HazardEvent.objects.filter(provider="mhews", hazard_type="dust_storm").count() == 1


def test_database_still_rejects_an_unregistered_provider_or_hazard_type():
    with pytest.raises((IntegrityError, ValidationError)):
        with transaction.atomic():
            hazard(provider="openweather").save()
    with pytest.raises((IntegrityError, ValidationError)):
        with transaction.atomic():
            hazard(hazard_type="thunderstorm", provider_event_id="other-1").save()


# ---------------------------------------------------------------------------
# Source URL allowlist
# ---------------------------------------------------------------------------


def test_mhews_source_urls_are_restricted_to_the_official_host():
    assert SOURCE_URL_ALLOWED_HOSTS["mhews"] == {"climweb.med.gov.sy"}
    validate_source_url(MHEWS_SOURCE, "mhews")
    for rejected in (
        "https://evil.example.com/api/cap/x.xml",
        "http://climweb.med.gov.sy/api/cap/x.xml",
        "https://climweb.med.gov.sy:8443/api/cap/x.xml",
        "https://user:pass@climweb.med.gov.sy/api/cap/x.xml",
    ):
        with pytest.raises(ValidationError):
            validate_source_url(rejected, "mhews")


def test_the_mhews_host_is_not_allowed_for_other_providers():
    with pytest.raises(ValidationError):
        validate_source_url(MHEWS_SOURCE, "usgs")
    with pytest.raises(ValidationError):
        validate_source_url("https://earthquake.usgs.gov/x", "mhews")


# ---------------------------------------------------------------------------
# Inertness: taxonomy without policy cannot raise an alert
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("hazard_type", ["dust_storm", "extreme_heat"])
def test_approved_weather_hazards_are_evaluated_on_official_warning_severity(hazard_type):
    """Approved in Phase 6C: an official warning, not a measured threshold."""

    policy = safety_policy.load_policy()
    rules = policy.rules_for(hazard_type)
    assert rules is not None
    assert safety_policy.CRITERION_BY_HAZARD[hazard_type] == "min_alert_level"
    assert {tier.criterion for tier in rules.tiers} == {"min_alert_level"}
    assert {tier.threshold for tier in rules.tiers} == {"red", "orange"}


@pytest.mark.parametrize("hazard_type", ["heavy_rain", "thunderstorm", "high_waves"])
def test_unmapped_hazards_remain_unconfigurable(hazard_type):
    """heavy_rain stays inert; thunderstorm/high_waves do not exist at all."""

    assert hazard_type not in safety_policy.CRITERION_BY_HAZARD
    tier = {
        "min_alert_level": "orange",
        "radius_km": 50,
        "severity": "high",
        "recommended_action": "increase_precautions",
    }
    with pytest.raises(ValidationError):
        safety_policy.validate_safety_setting(
            safety_policy.POLICY_SETTING_KEY,
            {"hazards": {hazard_type: {"max_event_age_hours": 24, "tiers": [tier]}}},
        )


def test_no_measurement_criterion_was_invented():
    """Only the two pre-existing criteria exist; no weather measurement."""

    assert set(safety_policy.CRITERION_BY_HAZARD.values()) == {
        "min_magnitude",
        "min_alert_level",
    }
    # Every tier key across the whole default policy stays within the schema
    # the policy engine already validated before this phase.
    allowed = {"min_magnitude", "min_alert_level", "radius_km", "severity", "recommended_action"}
    for rules in safety_policy.DEFAULT_POLICY["hazards"].values():
        for tier in rules["tiers"]:
            assert set(tier) <= allowed, set(tier) - allowed


def test_flood_policy_is_unchanged_by_this_phase():
    tiers = safety_policy.DEFAULT_POLICY["hazards"]["flood"]["tiers"]
    assert [tier["min_alert_level"] for tier in tiers] == ["red", "orange"]
    assert [tier["severity"] for tier in tiers] == ["critical", "high"]
    assert safety_policy.DEFAULT_POLICY["hazards"]["flood"]["max_event_age_hours"] == 72


def test_no_cap_severity_mapping_exists_anywhere_yet():
    """Guards against a CAP severity mapping being added without approval."""

    import apps.safety.models as models_module

    source = "".join(
        open(module.__file__, encoding="utf-8").read()
        for module in (models_module, safety_policy)
    ).lower()
    for cap_severity in ("extreme", "severe", "moderate", "minor"):
        assert f'"{cap_severity}"' not in source
