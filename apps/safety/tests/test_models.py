from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.safety.models import (
    HAZARD_PAYLOAD_MAX_BYTES,
    HazardEvent,
    ProjectSafetyAlert,
    payload_size_bytes,
    sanitize_hazard_payload,
    validate_source_url,
)
from apps.safety.tests.helpers import NOW, make_project


pytestmark = pytest.mark.django_db


def hazard(**overrides):
    values = {
        "provider": "usgs",
        "provider_event_id": "us-model-1",
        "hazard_type": "earthquake",
        "title": "Synthetic",
        "latitude": Decimal("30.1"),
        "longitude": Decimal("31.2"),
        "occurred_at": NOW,
        "provider_updated_at": NOW,
        "last_seen_at": NOW,
    }
    values.update(overrides)
    return HazardEvent(**values)


def alert_for(project, event, **overrides):
    values = {
        "project": project,
        "hazard_event": event,
        "hazard_type": event.hazard_type,
        "severity": "high",
        "distance_km": Decimal("12.50"),
        "project_latitude": project.latitude,
        "project_longitude": project.longitude,
        "rule_code": "earthquake.m5_5_r100",
        "recommended_action": "suspend_outdoor_work",
    }
    values.update(overrides)
    return ProjectSafetyAlert(**values)


def test_provider_identity_is_unique():
    hazard().save()
    with pytest.raises(IntegrityError), transaction.atomic():
        hazard(title="Duplicate").save()


@pytest.mark.parametrize(
    "overrides",
    [
        {"latitude": Decimal("95")},
        {"longitude": Decimal("-181")},
        {"hazard_type": "tsunami"},
        {"provider": "twitter"},
        {"provider_status": "unknown"},
        {"alert_level": "purple"},
        {"provider_event_id": ""},
        {"revision": 0},
    ],
)
def test_database_constraints_reject_invalid_hazards(overrides):
    with pytest.raises(IntegrityError), transaction.atomic():
        hazard(**{"provider_event_id": "us-bad", **overrides}).save()


@pytest.mark.parametrize(
    "url",
    [
        "http://earthquake.usgs.gov/event",
        "https://evil.example/event",
        "https://user:pass@earthquake.usgs.gov/event",
        "https://earthquake.usgs.gov:8443/event",
        "javascript:alert(1)",
        "https://www.gdacs.org/report",
    ],
)
def test_source_url_must_be_https_on_provider_host(url):
    with pytest.raises(ValidationError):
        validate_source_url(url, "usgs")


def test_source_url_allows_provider_pages_and_blank():
    validate_source_url("", "usgs")
    validate_source_url("https://earthquake.usgs.gov/earthquakes/eventpage/us1", "usgs")
    validate_source_url("https://www.gdacs.org/report.aspx?eventid=1", "gdacs")
    hazard(source_url="https://earthquake.usgs.gov/x").full_clean()


def test_payload_sanitizer_drops_secrets_and_bounds_size():
    sanitized = sanitize_hazard_payload(
        {
            "mag": 6.1,
            "api_key": "never-store",
            "Authorization": "Bearer x",
            "nested": {"token": "x", "place": "somewhere", "deep": {"deeper": {"deepest": 1}}},
            "long": "x" * 5000,
            "items": list(range(500)),
            "nan": float("nan"),
            7: "non-string key",
        }
    )
    assert "api_key" not in sanitized and "Authorization" not in sanitized
    assert "token" not in sanitized["nested"]
    assert len(sanitized["long"]) == 1000
    assert len(sanitized["items"]) == 50
    assert sanitized["nan"] is None
    assert 7 not in sanitized
    assert sanitize_hazard_payload("not a dict") == {}
    huge = {f"k{i}": "v" * 900 for i in range(60)}
    assert sanitize_hazard_payload(huge) == {"payload_truncated": True}


def test_model_clean_rejects_oversized_payload():
    event = hazard(payload={"blob": ["x" * 1000] * 40})
    assert payload_size_bytes(event.payload) > HAZARD_PAYLOAD_MAX_BYTES
    with pytest.raises(ValidationError):
        event.full_clean()


def test_alert_uniqueness_and_status_field_constraints(super_admin_user):
    project = make_project(super_admin_user)
    event = hazard()
    event.save()
    alert_for(project, event).save()
    with pytest.raises(IntegrityError), transaction.atomic():
        alert_for(project, event).save()

    other_project = make_project(super_admin_user, name="Other")
    with pytest.raises(IntegrityError), transaction.atomic():
        alert_for(other_project, event, status="actioned").save()
    with pytest.raises(IntegrityError), transaction.atomic():
        alert_for(other_project, event, recommended_action="other").save()
    with pytest.raises(IntegrityError), transaction.atomic():
        alert_for(other_project, event, severity="extreme").save()


def test_alert_snapshot_is_immutable_and_cannot_be_deleted(super_admin_user):
    project = make_project(super_admin_user)
    event = hazard()
    event.save()
    alert = alert_for(project, event)
    alert.save()

    alert.project_latitude = Decimal("10.000000")
    with pytest.raises(ValidationError):
        alert.save()
    alert.refresh_from_db()
    with pytest.raises(ValidationError):
        alert.delete()


def test_alert_clean_requires_matching_hazard_type_and_dismissal_reason(super_admin_user):
    project = make_project(super_admin_user)
    event = hazard()
    event.save()
    with pytest.raises(ValidationError):
        alert_for(project, event, hazard_type="flood").full_clean(validate_constraints=False)
    with pytest.raises(ValidationError):
        alert_for(
            project,
            event,
            status="dismissed",
            resolved_by=super_admin_user,
            resolved_at=NOW,
            resolution_notes="   ",
        ).full_clean(validate_constraints=False)
