"""Synthetic provider payloads shaped like the USGS and GDACS feeds.

These are hand-written test fixtures, not captured live data.
"""

from apps.safety.tests.helpers import NOW


NOW_MS = int(NOW.timestamp() * 1000)


def usgs_feature(
    event_id="us7000test",
    *,
    mag=6.0,
    latitude=30.341200,
    longitude=31.235700,
    depth=10.0,
    time_ms=NOW_MS,
    updated_ms=NOW_MS,
    status="reviewed",
    event_type="earthquake",
    alert=None,
    url="default",
    **extra_properties,
):
    properties = {
        "mag": mag,
        "magType": "mww",
        "place": "Synthetic region",
        "time": time_ms,
        "updated": updated_ms,
        "url": (
            f"https://earthquake.usgs.gov/earthquakes/eventpage/{event_id}" if url == "default" else url
        ),
        "detail": f"https://earthquake.usgs.gov/fdsnws/event/1/query?eventid={event_id}",
        "status": status,
        "alert": alert,
        "tsunami": 0,
        "net": "us",
        "type": event_type,
        "title": f"M {mag} - Synthetic region",
    }
    properties.update(extra_properties)
    return {
        "type": "Feature",
        "id": event_id,
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [longitude, latitude, depth]},
    }


def usgs_feed(*features):
    return {
        "type": "FeatureCollection",
        "metadata": {"generated": NOW_MS, "status": 200, "count": len(features)},
        "features": list(features),
    }


def gdacs_feature(
    event_type="FL",
    event_id=1000123,
    *,
    alert_level="Orange",
    episode_alert_level=None,
    latitude=30.100000,
    longitude=31.240000,
    from_date="2026-09-15T10:00:00",
    to_date="2026-09-18T00:00:00",
    date_modified="2026-09-15T11:00:00",
    is_current="true",
    source=None,
    source_id=None,
    severity=None,
    report_url="default",
):
    properties = {
        "eventtype": event_type,
        "eventid": event_id,
        "episodeid": 5,
        "name": f"{alert_level} {event_type} alert (synthetic)",
        "alertlevel": alert_level,
        "alertscore": 2,
        "country": "Synthetic",
        "iscurrent": is_current,
        "istemporary": "false",
        "fromdate": from_date,
        "todate": to_date,
        "datemodified": date_modified,
        "url": {
            "report": (
                f"https://www.gdacs.org/report.aspx?eventid={event_id}&eventtype={event_type}"
                if report_url == "default"
                else report_url
            ),
            "geometry": "https://www.gdacs.org/gdacsapi/api/polygons/getgeometry",
        },
        "htmldescription": "<b>not stored</b>",
    }
    if episode_alert_level is not None:
        properties["episodealertlevel"] = episode_alert_level
    if source is not None:
        properties["source"] = source
    if source_id is not None:
        properties["sourceid"] = source_id
    if severity is not None:
        properties["severitydata"] = severity
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
    }


def gdacs_feed(*features):
    return {"type": "FeatureCollection", "features": list(features)}
