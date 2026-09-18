from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.safety.providers import gdacs
from apps.safety.providers.base import MalformedProviderPayload
from apps.safety.tests.provider_samples import gdacs_feature, gdacs_feed


def _utc(*args):
    return datetime(*args, tzinfo=dt_timezone.utc)


def test_flood_is_normalized_with_type_scoped_identity_and_utc_dates():
    batch = gdacs.normalize_feed(
        gdacs_feed(gdacs_feature(alert_level="Orange", episode_alert_level="Red", severity={"severity": 3, "severitytext": "Magnitude 3", "severityunit": ""})),
        usgs_enabled=True,
    )

    event = batch.events[0]
    assert event.provider == "gdacs"
    assert event.provider_event_id == "FL:1000123"
    assert event.hazard_type == "flood"
    assert event.alert_level == "red"
    assert event.magnitude is None
    assert event.occurred_at == _utc(2026, 9, 15, 10) == event.valid_from
    assert event.valid_until == _utc(2026, 9, 18)
    assert event.provider_updated_at == _utc(2026, 9, 15, 11)
    assert event.provider_status == "active"
    assert event.title == "Orange FL alert (synthetic)"
    assert event.source_url.startswith("https://www.gdacs.org/report.aspx?")
    assert event.provider_severity == "red Magnitude 3"
    assert "htmldescription" not in event.payload and "url" not in event.payload
    assert event.payload["episodeid"] == 5


@pytest.mark.parametrize(
    "event_type,hazard_type",
    [("TC", "tropical_cyclone"), ("VO", "volcano"), ("WF", "wildfire"), ("fl", "flood")],
)
def test_supported_event_types(event_type, hazard_type):
    batch = gdacs.normalize_feed(gdacs_feed(gdacs_feature(event_type)), usgs_enabled=True)
    assert batch.events[0].hazard_type == hazard_type
    assert batch.events[0].provider_event_id == f"{event_type.upper()}:1000123"


def test_non_current_events_are_expired_and_explicit_utc_offsets_are_respected():
    batch = gdacs.normalize_feed(
        gdacs_feed(gdacs_feature(is_current="false", from_date="2026-09-15T12:00:00+02:00", date_modified="2026-09-15T11:00:00Z")),
        usgs_enabled=True,
    )
    event = batch.events[0]
    assert event.provider_status == "expired"
    assert event.occurred_at == _utc(2026, 9, 15, 10)


def test_drought_and_unknown_types_are_unsupported():
    batch = gdacs.normalize_feed(gdacs_feed(gdacs_feature("DR"), gdacs_feature("XX"), gdacs_feature()), usgs_enabled=True)
    assert batch.records_unsupported == 2 and len(batch.events) == 1


def test_earthquake_citing_usgs_is_deferred_and_the_citation_is_recorded():
    feature = gdacs_feature("EQ", 1500001, source="NEIC", source_id="us7000test")
    batch = gdacs.normalize_feed(gdacs_feed(feature), usgs_enabled=True)
    assert batch.events == []
    assert batch.records_deferred_to_usgs == 1
    assert batch.deferred_event_ids == ["EQ:1500001"]
    assert batch.records_reconciled == 1
    assert batch.reconciliations == [{"gdacs_event_id": "EQ:1500001", "usgs_event_id": "us7000test"}]


@pytest.mark.parametrize(
    "source,source_id",
    [("NEIC", ""), ("NEIC", "123456789"), ("EMSC", "20260915_0001"), (None, None)],
)
def test_every_earthquake_is_deferred_while_usgs_is_enabled(source, source_id):
    feature = gdacs_feature("EQ", 1500002, alert_level="Red", source=source, source_id=source_id)
    batch = gdacs.normalize_feed(gdacs_feed(feature), usgs_enabled=True)
    assert batch.events == []
    assert (batch.records_deferred_to_usgs, batch.records_reconciled) == (1, 0)
    assert batch.records_malformed == 0 and batch.records_unsupported == 0


@pytest.mark.parametrize(
    "source,source_id",
    [("NEIC", "us7000test"), ("NEIC", "123456789"), ("NEIC", ""), ("EMSC", "20260915_0001"), (None, None)],
)
def test_earthquake_is_kept_as_gdacs_event_when_usgs_is_disabled(source, source_id):
    feature = gdacs_feature(
        "EQ",
        1500002,
        alert_level="Red",
        source=source,
        source_id=source_id,
        severity={"severity": 6.4, "severitytext": "Magnitude 6.4M", "severityunit": "M"},
    )
    batch = gdacs.normalize_feed(gdacs_feed(feature), usgs_enabled=False)
    assert (batch.records_deferred_to_usgs, batch.records_reconciled) == (0, 0)
    event = batch.events[0]
    assert (event.provider, event.provider_event_id, event.hazard_type) == ("gdacs", "EQ:1500002", "earthquake")
    assert event.magnitude == Decimal("6.4")


def _broken(**overrides):
    return gdacs_feature(event_id=1999999, **overrides)


@pytest.mark.parametrize(
    "feature",
    [
        "not a feature",
        {"type": "Feature", "properties": "x"},
        _broken(alert_level="Purple"),
        _broken(alert_level=""),
        _broken(from_date="15/09/2026"),
        _broken(from_date=None),
        _broken(to_date="2026-09-01T00:00:00"),
        _broken(latitude=95.0),
        _broken(longitude="west"),
    ],
)
def test_malformed_records_are_isolated(feature):
    batch = gdacs.normalize_feed(gdacs_feed(gdacs_feature(), feature, gdacs_feature("TC", 1000555)), usgs_enabled=True)
    assert batch.records_malformed == 1
    assert [event.provider_event_id for event in batch.events] == ["FL:1000123", "TC:1000555"]


def test_invalid_event_id_is_malformed():
    feature = gdacs_feature()
    feature["properties"]["eventid"] = "12a"
    batch = gdacs.normalize_feed(gdacs_feed(feature), usgs_enabled=True)
    assert batch.records_malformed == 1


def test_unapproved_report_url_is_dropped():
    batch = gdacs.normalize_feed(gdacs_feed(gdacs_feature(report_url="https://gdacs.org.evil.example/x")), usgs_enabled=True)
    assert batch.events[0].source_url == ""


@pytest.mark.parametrize("document", [None, {"type": "FeatureCollection", "features": "x"}, {"features": []}])
def test_invalid_schema_rejects_whole_batch(document):
    with pytest.raises(MalformedProviderPayload):
        gdacs.normalize_feed(document, usgs_enabled=True)


def test_fetch_passes_allowlist_and_usgs_reconciliation_setting(settings):
    settings.SAFETY_USGS_ENABLED = False
    feed = gdacs_feed(gdacs_feature("EQ", 1500003, source="NEIC", source_id="us7000test", severity={"severity": 6, "severityunit": "M"}))
    with patch.object(gdacs, "fetch_json", return_value=feed) as fetch_json:
        batch = gdacs.GdacsProvider().fetch()
    assert fetch_json.call_args.kwargs["allowed_hosts"] == frozenset({"www.gdacs.org", "gdacs.org"})
    assert batch.records_reconciled == 0 and len(batch.events) == 1
