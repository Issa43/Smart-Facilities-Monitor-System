"""USGS earthquake GeoJSON summary feed adapter.

Feed format: https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
Each Feature has a stable ``id``; ``properties.updated`` (epoch ms) identifies
revisions; ``properties.status == "deleted"`` marks a withdrawn event.
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
    epoch_milliseconds,
    finite_decimal,
    require_mapping,
    safe_source_url,
)
from .http import fetch_json


PROVIDER = "usgs"
ALLOWED_HOSTS = frozenset({"earthquake.usgs.gov"})
MAX_FEATURES = 10000
USGS_EVENT_ID_PATTERN = re.compile(r"^[a-z0-9]{2,8}[a-z0-9_-]{1,40}$", re.IGNORECASE)
PAGER_ALERT_LEVELS = {"green": "green", "orange": "orange", "red": "red"}
PAYLOAD_PROPERTIES = (
    "mag",
    "magType",
    "place",
    "time",
    "updated",
    "status",
    "alert",
    "tsunami",
    "sig",
    "net",
    "code",
    "type",
    "felt",
    "cdi",
    "mmi",
)


def _normalize_feature(feature):
    feature = require_mapping(feature, "feature")
    event_id = feature.get("id")
    if not isinstance(event_id, str) or not USGS_EVENT_ID_PATTERN.match(event_id):
        raise RejectedProviderRecord("id_invalid")
    properties = require_mapping(feature.get("properties"), "properties")
    geometry = require_mapping(feature.get("geometry"), "geometry")
    if geometry.get("type") != "Point":
        raise RejectedProviderRecord("geometry_not_point")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise RejectedProviderRecord("coordinates_invalid")
    longitude = finite_decimal(coordinates[0], "longitude", required=True, minimum=Decimal("-180"), maximum=Decimal("180"))
    latitude = finite_decimal(coordinates[1], "latitude", required=True, minimum=Decimal("-90"), maximum=Decimal("90"))
    depth = (
        finite_decimal(coordinates[2], "depth", minimum=Decimal("-15"), maximum=Decimal("1000"))
        if len(coordinates) > 2
        else None
    )
    magnitude = finite_decimal(properties.get("mag"), "magnitude", minimum=Decimal("-2"), maximum=Decimal("10"))
    occurred_at = epoch_milliseconds(properties.get("time"), "time")
    updated_at = epoch_milliseconds(properties.get("updated"), "updated", required=False) or occurred_at
    if updated_at < occurred_at:
        updated_at = occurred_at

    status = properties.get("status")
    provider_status = "withdrawn" if status == "deleted" else "active"
    alert = properties.get("alert")
    mag_type = bounded_text(properties.get("magType"), 8)
    magnitude_text = f"M{magnitude}" if magnitude is not None else "M?"
    title = bounded_text(properties.get("title"), 255) or bounded_text(
        f"{magnitude_text} - {bounded_text(properties.get('place'), 200)}", 255
    )
    return NormalizedHazardEvent(
        provider=PROVIDER,
        provider_event_id=event_id,
        hazard_type="earthquake",
        title=title,
        latitude=latitude,
        longitude=longitude,
        depth_km=depth,
        magnitude=magnitude,
        occurred_at=occurred_at,
        provider_updated_at=updated_at,
        provider_severity=bounded_text(f"{magnitude_text} {mag_type}", 32),
        alert_level=PAGER_ALERT_LEVELS.get(alert) if isinstance(alert, str) else None,
        source_url=safe_source_url(properties.get("url"), PROVIDER),
        provider_status=provider_status,
        payload={key: properties.get(key) for key in PAYLOAD_PROPERTIES if key in properties},
    )


def normalize_feed(document):
    """Translate a USGS FeatureCollection into a ProviderBatch."""

    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise MalformedProviderPayload("not_feature_collection")
    features = document.get("features")
    if not isinstance(features, list):
        raise MalformedProviderPayload("features_not_list")
    if len(features) > MAX_FEATURES:
        raise MalformedProviderPayload("too_many_features")

    batch = ProviderBatch(provider=PROVIDER, records_received=len(features))
    for feature in features:
        properties = feature.get("properties") if isinstance(feature, dict) else None
        if isinstance(properties, dict) and properties.get("type") not in (None, "earthquake"):
            # Quarry blasts, explosions, and similar non-natural events.
            batch.records_unsupported += 1
            continue
        try:
            batch.events.append(_normalize_feature(feature))
        except RejectedProviderRecord:
            batch.records_malformed += 1
    return batch


class UsgsEarthquakeProvider:
    code = PROVIDER

    def enabled(self):
        return bool(settings.SAFETY_USGS_ENABLED)

    def fetch(self):
        document = fetch_json(
            settings.SAFETY_USGS_FEED_URL,
            allowed_hosts=ALLOWED_HOSTS,
            timeout_seconds=settings.SAFETY_PROVIDER_TIMEOUT_SECONDS,
            max_bytes=settings.SAFETY_PROVIDER_MAX_BYTES,
        )
        return normalize_feed(document)
