"""GDACS event list adapter (GeoJSON ``EVENTS4APP`` feed).

Identity: ``provider_event_id = "<eventtype>:<eventid>"``. GDACS event ids are
scoped by event type, so the type prefix prevents collisions. Each new episode
updates ``datemodified``, which becomes a new revision of the same event.

Earthquakes: USGS is the authoritative earthquake source. While USGS polling
is enabled (``SAFETY_USGS_ENABLED``), every GDACS earthquake is skipped before
ingestion and counted as deferred to USGS. Live GDACS earthquakes cite
``source: NEIC`` with an empty ``sourceid``, so no reliable identifier exists
to correlate the two feeds, and no coordinate/time/magnitude heuristic is used.
When a record does cite a USGS event id, that pair is also logged. The switch
is the configuration flag, not runtime availability, so a USGS outage never
re-enables duplicate earthquake ingestion. With USGS polling disabled, GDACS
earthquakes are ingested as their own ``gdacs`` events.
"""

import re
from decimal import Decimal

from django.conf import settings

from apps.safety.services import NormalizedHazardEvent

from .base import (
    MalformedProviderPayload,
    ProviderBatch,
    RejectedProviderRecord,
    bounded_text,
    finite_decimal,
    require_mapping,
    safe_source_url,
    utc_datetime,
)
from .http import fetch_json


PROVIDER = "gdacs"
ALLOWED_HOSTS = frozenset({"www.gdacs.org", "gdacs.org"})
MAX_FEATURES = 5000
HAZARD_BY_EVENT_TYPE = {
    "EQ": "earthquake",
    "TC": "tropical_cyclone",
    "FL": "flood",
    "VO": "volcano",
    "WF": "wildfire",
}
ALERT_LEVELS = {"green": "green", "orange": "orange", "red": "red"}
ALERT_RANK = {"green": 0, "orange": 1, "red": 2}
USGS_SOURCE_NAMES = frozenset({"NEIC", "USGS"})
PAYLOAD_PROPERTIES = (
    "eventtype",
    "eventid",
    "episodeid",
    "alertlevel",
    "episodealertlevel",
    "alertscore",
    "episodealertscore",
    "country",
    "iscurrent",
    "istemporary",
    "fromdate",
    "todate",
    "datemodified",
    "source",
    "sourceid",
)
_EVENT_ID_PATTERN = re.compile(r"^[0-9]{1,12}$")
# Reconciliation requires a network-prefixed USGS id such as "us7000abcd".
# Bare numbers or free text never qualify, so no false merge can occur.
_USGS_CITATION_PATTERN = re.compile(r"^[a-z]{2}[a-z0-9]{6,14}$")


def _alert_level(properties):
    """Use the more severe of the event and current-episode alert levels."""

    levels = []
    for key in ("alertlevel", "episodealertlevel"):
        value = properties.get(key)
        if value in (None, ""):
            continue
        if not isinstance(value, str) or value.strip().lower() not in ALERT_LEVELS:
            raise RejectedProviderRecord(f"{key}_invalid")
        levels.append(ALERT_LEVELS[value.strip().lower()])
    if not levels:
        raise RejectedProviderRecord("alertlevel_missing")
    return max(levels, key=ALERT_RANK.__getitem__)


def _is_false(value):
    return value is False or (isinstance(value, str) and value.strip().lower() == "false")


def usgs_source_event_id(properties):
    """Return the cited USGS event id, or None when there is no reliable one."""

    source = properties.get("source")
    source_id = properties.get("sourceid")
    if (
        isinstance(source, str)
        and source.strip().upper() in USGS_SOURCE_NAMES
        and isinstance(source_id, str)
        and _USGS_CITATION_PATTERN.match(source_id.strip().lower())
    ):
        return source_id.strip().lower()
    return None


def _normalize_feature(feature, event_type, hazard_type):
    properties = feature["properties"]
    raw_event_id = properties.get("eventid")
    event_id = str(raw_event_id).strip() if isinstance(raw_event_id, (str, int)) and not isinstance(raw_event_id, bool) else ""
    if not _EVENT_ID_PATTERN.match(event_id):
        raise RejectedProviderRecord("eventid_invalid")

    geometry = require_mapping(feature.get("geometry"), "geometry")
    if geometry.get("type") != "Point":
        raise RejectedProviderRecord("geometry_not_point")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise RejectedProviderRecord("coordinates_invalid")
    longitude = finite_decimal(coordinates[0], "longitude", required=True, minimum=Decimal("-180"), maximum=Decimal("180"))
    latitude = finite_decimal(coordinates[1], "latitude", required=True, minimum=Decimal("-90"), maximum=Decimal("90"))

    alert_level = _alert_level(properties)
    occurred_at = utc_datetime(properties.get("fromdate"), "fromdate")
    valid_until = utc_datetime(properties.get("todate"), "todate", required=False)
    if valid_until is not None and valid_until < occurred_at:
        raise RejectedProviderRecord("todate_before_fromdate")
    updated_at = utc_datetime(properties.get("datemodified"), "datemodified", required=False) or occurred_at

    magnitude = None
    severity_text = ""
    severity = properties.get("severitydata")
    if isinstance(severity, dict):
        severity_text = bounded_text(severity.get("severitytext"), 24)
        if hazard_type == "earthquake" and bounded_text(severity.get("severityunit"), 8).upper() == "M":
            magnitude = finite_decimal(severity.get("severity"), "magnitude", minimum=Decimal("-2"), maximum=Decimal("10"))

    url = properties.get("url")
    report_url = url.get("report") if isinstance(url, dict) else None
    title = bounded_text(properties.get("name"), 255) or bounded_text(
        properties.get("eventname"), 255
    ) or f"GDACS {event_type} {event_id}"
    payload = {key: properties.get(key) for key in PAYLOAD_PROPERTIES if key in properties}
    if isinstance(severity, dict):
        payload["severitydata"] = {
            key: severity.get(key) for key in ("severity", "severitytext", "severityunit") if key in severity
        }
    return NormalizedHazardEvent(
        provider=PROVIDER,
        provider_event_id=f"{event_type}:{event_id}",
        hazard_type=hazard_type,
        title=title,
        latitude=latitude,
        longitude=longitude,
        magnitude=magnitude,
        occurred_at=occurred_at,
        valid_from=occurred_at,
        valid_until=valid_until,
        provider_updated_at=updated_at,
        provider_severity=bounded_text(f"{alert_level} {severity_text}", 32),
        alert_level=alert_level,
        source_url=safe_source_url(report_url, PROVIDER),
        provider_status="expired" if _is_false(properties.get("iscurrent")) else "active",
        payload=payload,
    )


def normalize_feed(document, *, usgs_enabled):
    """Translate a GDACS FeatureCollection into a ProviderBatch."""

    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise MalformedProviderPayload("not_feature_collection")
    features = document.get("features")
    if not isinstance(features, list):
        raise MalformedProviderPayload("features_not_list")
    if len(features) > MAX_FEATURES:
        raise MalformedProviderPayload("too_many_features")

    batch = ProviderBatch(provider=PROVIDER, records_received=len(features))
    for feature in features:
        try:
            feature = require_mapping(feature, "feature")
            properties = require_mapping(feature.get("properties"), "properties")
            event_type = properties.get("eventtype")
            event_type = event_type.strip().upper() if isinstance(event_type, str) else ""
            hazard_type = HAZARD_BY_EVENT_TYPE.get(event_type)
            if hazard_type is None:
                # Droughts and unknown event types are outside Safety scope.
                batch.records_unsupported += 1
                continue
            if hazard_type == "earthquake" and usgs_enabled:
                gdacs_id = f"EQ:{bounded_text(properties.get('eventid'), 12)}"
                batch.records_deferred_to_usgs += 1
                batch.deferred_event_ids.append(gdacs_id)
                usgs_id = usgs_source_event_id(properties)
                if usgs_id is not None:
                    batch.records_reconciled += 1
                    batch.reconciliations.append(
                        {"gdacs_event_id": gdacs_id, "usgs_event_id": usgs_id}
                    )
                continue
            batch.events.append(_normalize_feature(feature, event_type, hazard_type))
        except RejectedProviderRecord:
            batch.records_malformed += 1
    return batch


class GdacsProvider:
    code = PROVIDER

    def enabled(self):
        return bool(settings.SAFETY_GDACS_ENABLED)

    def fetch(self):
        document = fetch_json(
            settings.SAFETY_GDACS_EVENTS_URL,
            allowed_hosts=ALLOWED_HOSTS,
            timeout_seconds=settings.SAFETY_PROVIDER_TIMEOUT_SECONDS,
            max_bytes=settings.SAFETY_PROVIDER_MAX_BYTES,
        )
        return normalize_feed(document, usgs_enabled=bool(settings.SAFETY_USGS_ENABLED))
