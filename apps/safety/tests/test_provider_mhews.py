"""Offline tests for the Syrian MHEWS CAP adapter (Phase 6C).

Fixtures are shaped from the verified official feed. No test performs a real
request: the adapter is exercised through parsed documents, and the global
network guard would fail any test that tried.
"""

from decimal import Decimal

import pytest

from apps.safety import geo
from apps.safety.providers import mhews
from apps.safety.providers.base import MalformedProviderPayload
from apps.safety.services import NormalizedHazardEvent


SENDER = "mhews@med.gov.sy"
# A square over eastern Syria, given in CAP order: "latitude,longitude".
SQUARE_CAP = "35.0,39.0 35.0,40.0 36.0,40.0 36.0,39.0 35.0,39.0"
SECOND_CAP = "33.0,36.0 33.0,37.0 34.0,37.0 34.0,36.0 33.0,36.0"


def cap(
    identifier="urn:oid:2.49.0.1.760.1.2026.9.14.7.4.0",
    *,
    sender=SENDER,
    status="Actual",
    msg_type="Alert",
    references="",
    event_code="OET-079",
    severity="Severe",
    polygons=(SQUARE_CAP,),
    headline="ارتفاع منسوب نهر الفرات",
    extra_area="",
    sent="2026-09-14T10:04:00+03:00",
):
    reference_element = f"<cap:references>{references}</cap:references>" if references else ""
    polygon_elements = "".join(f"<cap:polygon>{p}</cap:polygon>" for p in polygons)
    code_element = (
        f"<cap:eventCode><cap:valueName>OET:v1.2</cap:valueName>"
        f"<cap:value>{event_code}</cap:value></cap:eventCode>"
        if event_code
        else ""
    )
    return f"""<?xml version='1.0' encoding='utf-8'?>
<cap:alert xmlns:cap="{mhews.CAP_NAMESPACE}">
<cap:identifier>{identifier}</cap:identifier>
<cap:sender>{sender}</cap:sender>
<cap:sent>{sent}</cap:sent>
<cap:status>{status}</cap:status>
<cap:msgType>{msg_type}</cap:msgType>
{reference_element}
<cap:scope>Public</cap:scope>
<cap:info>
<cap:language>ar</cap:language>
<cap:category>Met</cap:category>
<cap:event>فيضان مفاجئ</cap:event>
<cap:urgency>Immediate</cap:urgency>
<cap:severity>{severity}</cap:severity>
<cap:certainty>Likely</cap:certainty>
{code_element}
<cap:effective>2026-09-14T08:00:00+03:00</cap:effective>
<cap:onset>2026-09-14T09:00:00+03:00</cap:onset>
<cap:expires>2026-10-15T20:00:00+03:00</cap:expires>
<cap:headline>{headline}</cap:headline>
<cap:description>وصف</cap:description>
<cap:web>https://climweb.med.gov.sy/alert</cap:web>
<cap:area><cap:areaDesc>حرم نهر الفرات</cap:areaDesc>{polygon_elements}</cap:area>
{extra_area}
</cap:info>
</cap:alert>"""


def parse(*documents):
    return mhews.normalize_documents([mhews.parse_xml(d) for d in documents])


def one(*documents):
    batch = parse(*documents)
    assert len(batch.events) == 1, batch
    return batch.events[0]


# ---------------------------------------------------------------------------
# Severity mapping (the approved Phase 6C decision)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "severity,expected",
    [("Extreme", "red"), ("Severe", "red"), ("Moderate", "orange"), ("Minor", "green")],
)
def test_approved_cap_severity_mapping(severity, expected):
    event = one(cap(severity=severity))
    assert event.alert_level == expected
    # The original CAP value survives the lossy normalization.
    assert event.provider_severity == severity


@pytest.mark.parametrize("severity", ["Unknown", "", "Catastrophic", "severe"])
def test_unmappable_severity_is_not_actionable(severity):
    batch = parse(cap(severity=severity))
    assert batch.events == []
    assert batch.records_received == 1


def test_extreme_and_severe_both_map_to_red_by_design():
    assert mhews.SEVERITY_TO_ALERT_LEVEL["Extreme"] == "red"
    assert mhews.SEVERITY_TO_ALERT_LEVEL["Severe"] == "red"
    assert "Unknown" not in mhews.SEVERITY_TO_ALERT_LEVEL
    assert set(mhews.SEVERITY_TO_ALERT_LEVEL.values()) <= {"green", "orange", "red"}


# ---------------------------------------------------------------------------
# Hazard taxonomy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code,hazard_type",
    [("OET-079", "flood"), ("OET-098", "extreme_heat"), ("OET-170", "dust_storm")],
)
def test_authorized_event_codes_map_to_existing_hazards(code, hazard_type):
    assert one(cap(event_code=code)).hazard_type == hazard_type


@pytest.mark.parametrize("code", ["OET-103", "OET-100"])
def test_out_of_scope_event_codes_are_never_mapped(code):
    """OET-103 is hydrological infrastructure; OET-100 is marine."""

    batch = parse(cap(event_code=code))
    assert batch.events == []
    assert batch.records_unsupported == 1


@pytest.mark.parametrize("code", ["", "OET-999", "OET-200", "TORNADO", "unknown"])
def test_unknown_event_codes_fail_closed(code):
    batch = parse(cap(event_code=code))
    assert batch.events == []


def test_no_guessed_thunderstorm_or_heavy_rain_mapping_exists():
    """Neither code is verified, so neither may appear in the mapping."""

    assert set(mhews.HAZARD_BY_EVENT_CODE) == {"OET-079", "OET-098", "OET-170"}
    assert "thunderstorm" not in mhews.HAZARD_BY_EVENT_CODE.values()
    assert "heavy_rain" not in mhews.HAZARD_BY_EVENT_CODE.values()
    assert "OET-103" not in mhews.HAZARD_BY_EVENT_CODE
    assert "OET-100" not in mhews.HAZARD_BY_EVENT_CODE


def test_free_text_is_never_used_to_infer_a_hazard_type():
    """A rain/storm headline with no supported code must not be classified."""

    for headline in ("أمطار غزيرة heavy rain", "عاصفة رعدية thunderstorm", "storm"):
        batch = parse(cap(event_code="OET-999", headline=headline))
        assert batch.events == []


# ---------------------------------------------------------------------------
# Sender, status and message type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sender", ["attacker@example.com", "", "mhews@med.gov.sy.evil.com"])
def test_unapproved_senders_are_rejected(sender):
    batch = parse(cap(sender=sender))
    assert batch.events == []
    assert batch.records_malformed == 1


@pytest.mark.parametrize("status", ["Test", "Exercise", "System", "Draft"])
def test_non_production_statuses_never_become_hazards(status):
    assert parse(cap(status=status)).events == []


@pytest.mark.parametrize("status", ["Live", "", "actual", "ACTUAL"])
def test_unknown_status_fails_closed(status):
    assert parse(cap(status=status)).events == []


@pytest.mark.parametrize("msg_type", ["Ack", "Error", "Announcement", ""])
def test_unsupported_message_types_are_skipped(msg_type):
    assert parse(cap(msg_type=msg_type)).events == []


# ---------------------------------------------------------------------------
# CAP identity: one logical hazard per warning chain
# ---------------------------------------------------------------------------

ROOT = "urn:oid:2.49.0.1.760.1.2026.8.14.13.42.0"
UPDATE_1 = "urn:oid:2.49.0.1.760.1.2026.8.21.19.10.0"
UPDATE_2 = "urn:oid:2.49.0.1.760.1.2026.9.2.17.56.0"


def reference_to(identifier):
    return f"{SENDER},{identifier},2026-08-21T19:10:00-00:00"


def test_alert_uses_its_own_identifier():
    assert one(cap(identifier=ROOT)).provider_event_id == ROOT


def test_update_resolves_to_the_root_alert():
    batch = parse(
        cap(identifier=ROOT),
        cap(identifier=UPDATE_1, msg_type="Update", references=reference_to(ROOT)),
    )
    assert {event.provider_event_id for event in batch.events} == {ROOT}
    assert len(batch.events) == 2


def test_update_of_update_resolves_to_the_same_root():
    batch = parse(
        cap(identifier=ROOT),
        cap(identifier=UPDATE_1, msg_type="Update", references=reference_to(ROOT)),
        cap(identifier=UPDATE_2, msg_type="Update", references=reference_to(UPDATE_1)),
    )
    assert {event.provider_event_id for event in batch.events} == {ROOT}
    assert len(batch.events) == 3


def test_cancel_resolves_to_the_root_and_withdraws():
    batch = parse(
        cap(identifier=ROOT),
        cap(identifier=UPDATE_1, msg_type="Cancel", references=reference_to(ROOT)),
    )
    cancel = [event for event in batch.events if event.provider_status == "withdrawn"]
    assert len(cancel) == 1
    assert cancel[0].provider_event_id == ROOT
    # A cancellation carries no actionable severity.
    assert cancel[0].alert_level is None


def test_reference_loops_are_bounded_and_do_not_hang():
    parents = {"a": "b", "b": "c", "c": "a"}
    assert mhews.resolve_root_identifier("a", parents) in parents
    deep = {str(i): str(i + 1) for i in range(50)}
    resolved = mhews.resolve_root_identifier("0", deep)
    assert resolved == str(mhews.MAX_REFERENCE_DEPTH)


def test_references_from_an_unapproved_sender_are_ignored():
    batch = parse(
        cap(
            identifier=UPDATE_1,
            msg_type="Update",
            references=f"attacker@example.com,{ROOT},2026-08-21T19:10:00-00:00",
        )
    )
    assert batch.events[0].provider_event_id == UPDATE_1


def test_reprocessing_the_same_documents_is_deterministic():
    first = parse(cap(identifier=ROOT))
    second = parse(cap(identifier=ROOT))
    assert first.events[0].provider_event_id == second.events[0].provider_event_id
    assert first.events[0].area_polygons == second.events[0].area_polygons


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def test_cap_latitude_longitude_is_converted_to_geojson_order():
    event = one(cap())
    ring = event.area_polygons[0][0]
    longitudes = [position[0] for position in ring]
    latitudes = [position[1] for position in ring]
    # Longitudes are ~39-40, latitudes ~35-36. Swapped order would invert these.
    assert min(longitudes) >= 39.0 and max(longitudes) <= 40.0
    assert min(latitudes) >= 35.0 and max(latitudes) <= 36.0
    assert geo.normalize_multipolygon(event.area_polygons) == event.area_polygons


def test_multiple_polygons_are_preserved_as_disjoint_components():
    event = one(cap(polygons=(SQUARE_CAP, SECOND_CAP)))
    assert len(event.area_polygons) == 2
    assert geo.point_in_multipolygon(35.5, 39.5, event.area_polygons) is True
    assert geo.point_in_multipolygon(33.5, 36.5, event.area_polygons) is True
    # The gap between the two components must not match.
    assert geo.point_in_multipolygon(34.5, 38.0, event.area_polygons) is False


@pytest.mark.parametrize(
    "polygon",
    ["", "35.0 39.0", "35.0,39.0 35.0,40.0", "x,39.0 35.0,40.0 36.0,40.0 35.0,39.0"],
)
def test_malformed_polygons_reject_the_alert_without_approximating(polygon):
    batch = parse(cap(polygons=(polygon,)))
    assert batch.events == []
    assert batch.records_malformed == 1


def test_an_alert_without_any_polygon_is_rejected():
    assert parse(cap(polygons=())).events == []


def test_reference_point_is_never_used_for_matching():
    """A reference point exists for display; the polygon decides matching."""

    event = one(cap())
    assert 35.0 <= float(event.latitude) <= 36.0
    assert 39.0 <= float(event.longitude) <= 40.0
    assert event.radius_km is None


# ---------------------------------------------------------------------------
# Timing, payload and transport safety
# ---------------------------------------------------------------------------


def test_cap_timing_is_preserved():
    event = one(cap())
    assert event.occurred_at.isoformat() == "2026-09-14T06:00:00+00:00"  # onset
    assert event.provider_updated_at.isoformat() == "2026-09-14T07:04:00+00:00"  # sent
    assert event.valid_until.isoformat() == "2026-10-15T17:00:00+00:00"  # expires


def test_payload_keeps_bounded_cap_facts_only():
    payload = one(cap()).payload
    assert payload["cap_event_code"] == "OET-079"
    assert payload["cap_severity"] == "Severe"
    assert payload["cap_urgency"] == "Immediate"
    assert payload["cap_certainty"] == "Likely"
    # No raw XML, no description body, no instruction text.
    assert not any("<cap:" in str(value) for value in payload.values())
    assert "cap_description" not in payload
    assert "cap_instruction" not in payload


def test_doctype_documents_are_refused():
    hostile = (
        '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        f'<cap:alert xmlns:cap="{mhews.CAP_NAMESPACE}"><cap:identifier>x</cap:identifier></cap:alert>'
    )
    with pytest.raises(MalformedProviderPayload):
        mhews.parse_xml(hostile)


def test_invalid_xml_is_refused():
    with pytest.raises(MalformedProviderPayload):
        mhews.parse_xml("<cap:alert>")


def test_only_approved_host_links_are_discoverable():
    feed = """<?xml version="1.0"?><rss version="2.0"><channel>
    <item><link>https://climweb.med.gov.sy/api/cap/a.xml</link></item>
    <item><link>https://evil.example.com/api/cap/b.xml</link></item>
    <item><link>http://climweb.med.gov.sy/api/cap/c.xml</link></item>
    </channel></rss>"""
    urls = mhews.cap_document_urls(mhews.parse_xml(feed))
    assert urls == ["https://climweb.med.gov.sy/api/cap/a.xml"]


def test_provider_is_disabled_by_default(settings):
    assert settings.SAFETY_WEATHER_ENABLED is False
    assert mhews.MhewsWarningProvider().enabled() is False
    settings.SAFETY_WEATHER_ENABLED = True
    assert mhews.MhewsWarningProvider().enabled() is True


def test_feed_url_is_fixed_and_not_environment_controlled(settings):
    assert settings.SAFETY_MHEWS_FEED_URL == "https://climweb.med.gov.sy/api/cap/rss.xml"
    assert mhews.ALLOWED_HOSTS == {"climweb.med.gov.sy"}


def test_normalized_events_are_the_shared_contract():
    assert isinstance(one(cap()), NormalizedHazardEvent)
    assert one(cap()).provider == "mhews"
