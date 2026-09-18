from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.safety.providers import usgs
from apps.safety.providers.base import MalformedProviderPayload
from apps.safety.tests.helpers import NOW, later
from apps.safety.tests.provider_samples import NOW_MS, usgs_feature, usgs_feed


def test_feature_is_normalized_into_the_safety_contract():
    batch = usgs.normalize_feed(usgs_feed(usgs_feature(alert="red")))

    assert (batch.records_received, batch.records_malformed, batch.records_unsupported) == (1, 0, 0)
    event = batch.events[0]
    assert event.provider == "usgs"
    assert event.provider_event_id == "us7000test"
    assert event.hazard_type == "earthquake"
    assert event.magnitude == Decimal("6.0")
    assert event.depth_km == Decimal("10.0")
    assert (event.latitude, event.longitude) == (Decimal("30.3412"), Decimal("31.2357"))
    assert event.occurred_at == NOW and event.provider_updated_at == NOW
    assert event.provider_status == "active"
    assert event.alert_level == "red"
    assert event.provider_severity == "M6.0 mww"
    assert event.title == "M 6.0 - Synthetic region"
    assert event.source_url == "https://earthquake.usgs.gov/earthquakes/eventpage/us7000test"
    assert event.radius_km is None
    assert "detail" not in event.payload and "url" not in event.payload
    assert event.payload["status"] == "reviewed"


def test_revision_deleted_status_and_alert_mapping():
    updated = int(later(10).timestamp() * 1000)
    batch = usgs.normalize_feed(
        usgs_feed(
            usgs_feature("us1revised", updated_ms=updated, alert="yellow"),
            usgs_feature("us2deleted", status="deleted"),
            usgs_feature("us3noupdate", updated_ms=None),
            usgs_feature("us4backdated", updated_ms=NOW_MS - 60_000),
        )
    )
    revised, deleted, no_update, backdated = batch.events
    assert revised.provider_updated_at == later(10)
    assert revised.alert_level is None and revised.payload["alert"] == "yellow"
    assert deleted.provider_status == "withdrawn"
    assert no_update.provider_updated_at == no_update.occurred_at
    assert backdated.provider_updated_at == backdated.occurred_at


def test_non_earthquake_events_are_counted_as_unsupported():
    batch = usgs.normalize_feed(usgs_feed(usgs_feature("us1blast", event_type="quarry blast"), usgs_feature()))
    assert batch.records_unsupported == 1 and len(batch.events) == 1


def test_unapproved_source_url_is_dropped_but_record_kept():
    batch = usgs.normalize_feed(
        usgs_feed(
            usgs_feature("us1evil", url="https://evil.example/phish"),
            usgs_feature("us2http", url="http://earthquake.usgs.gov/x"),
            usgs_feature("us3none", url=None),
        )
    )
    assert [event.source_url for event in batch.events] == ["", "", ""]


def _broken(mutator):
    feature = usgs_feature("us9broken")
    mutator(feature)
    return feature


@pytest.mark.parametrize(
    "feature",
    [
        "not a feature",
        _broken(lambda f: f.pop("id")),
        _broken(lambda f: f.update(id=12345)),
        _broken(lambda f: f.update(id="bad id with spaces")),
        _broken(lambda f: f.update(properties=None)),
        _broken(lambda f: f.update(geometry={"type": "Polygon", "coordinates": []})),
        _broken(lambda f: f["geometry"].update(coordinates=[31.2])),
        _broken(lambda f: f["geometry"].update(coordinates=[31.2, 91.0, 10])),
        _broken(lambda f: f["geometry"].update(coordinates=["east", 30, 10])),
        _broken(lambda f: f["geometry"].update(coordinates=[31.2, 30.0, 5000])),
        _broken(lambda f: f["properties"].update(mag=True)),
        _broken(lambda f: f["properties"].update(mag="strong")),
        _broken(lambda f: f["properties"].update(mag=12)),
        _broken(lambda f: f["properties"].update(time="yesterday")),
        _broken(lambda f: f["properties"].pop("time")),
        _broken(lambda f: f["properties"].update(time=float("inf"))),
    ],
)
def test_malformed_records_are_isolated_from_valid_ones(feature):
    batch = usgs.normalize_feed(usgs_feed(usgs_feature("us1good"), feature, usgs_feature("us2good")))
    assert batch.records_malformed == 1
    assert [event.provider_event_id for event in batch.events] == ["us1good", "us2good"]


def test_null_magnitude_is_allowed_and_left_to_policy():
    batch = usgs.normalize_feed(usgs_feed(usgs_feature("us1nomag", mag=None)))
    assert batch.events[0].magnitude is None
    assert batch.events[0].title == "M None - Synthetic region"


@pytest.mark.parametrize(
    "document",
    [None, [], "text", {"type": "Feature"}, {"type": "FeatureCollection"}, {"type": "FeatureCollection", "features": {}}],
)
def test_invalid_feed_schema_rejects_whole_batch(document):
    with pytest.raises(MalformedProviderPayload):
        usgs.normalize_feed(document)


def test_oversized_feature_list_rejects_whole_batch():
    with patch.object(usgs, "MAX_FEATURES", 2):
        with pytest.raises(MalformedProviderPayload):
            usgs.normalize_feed(usgs_feed(usgs_feature("us1a"), usgs_feature("us1b"), usgs_feature("us1c")))


def test_fetch_uses_only_configured_endpoint_allowlist_and_bounds(settings):
    settings.SAFETY_USGS_FEED_URL = "https://earthquake.usgs.gov/test.geojson"
    settings.SAFETY_PROVIDER_TIMEOUT_SECONDS = 7
    settings.SAFETY_PROVIDER_MAX_BYTES = 123456
    with patch.object(usgs, "fetch_json", return_value=usgs_feed(usgs_feature())) as fetch_json:
        batch = usgs.UsgsEarthquakeProvider().fetch()
    fetch_json.assert_called_once_with(
        "https://earthquake.usgs.gov/test.geojson",
        allowed_hosts=frozenset({"earthquake.usgs.gov"}),
        timeout_seconds=7,
        max_bytes=123456,
    )
    assert len(batch.events) == 1
