"""Syrian MHEWS official warning adapter (CAP 1.2).

Ministry of Emergency and Disaster Management, Multi-Hazard Early Warning
System. The RSS feed is only a discovery index; each item links to a CAP 1.2
document on the same approved host, and the CAP document is the authority.

This adapter only translates. It makes no policy decision, creates no alert,
and sends nothing. Everything it cannot represent exactly — an unknown event
code, an unmappable severity, a non-production status, malformed geometry — is
counted and skipped rather than approximated.

Provider content is untrusted: no link inside a CAP document is ever fetched,
XML document type declarations are rejected outright, and only the approved
host may be contacted.
"""

import xml.etree.ElementTree as ET

from django.conf import settings

from .base import (
    MalformedProviderPayload,
    ProviderBatch,
    RejectedProviderRecord,
    bounded_text,
    safe_source_url,
    utc_datetime,
)
from .http import fetch_body


PROVIDER = "mhews"
ALLOWED_HOSTS = {"climweb.med.gov.sy"}
CAP_NAMESPACE = "urn:oasis:names:tc:emergency:cap:1.2"
NS = {"cap": CAP_NAMESPACE}

# Approved senders. A CAP document from anyone else is rejected outright.
APPROVED_SENDERS = {"mhews@med.gov.sy"}

# Only real warnings become Safety hazards. Test, Exercise, System and Draft
# messages are counted and dropped; anything unrecognized fails closed.
PRODUCTION_STATUS = "Actual"
KNOWN_STATUSES = {"Actual", "Exercise", "System", "Test", "Draft"}

MSG_TYPE_ALERT = "Alert"
MSG_TYPE_UPDATE = "Update"
MSG_TYPE_CANCEL = "Cancel"
KNOWN_MSG_TYPES = {MSG_TYPE_ALERT, MSG_TYPE_UPDATE, MSG_TYPE_CANCEL, "Ack", "Error"}

# Authorized CAP severity -> normalized SFLMS alert level (Phase 6C decision).
# Deliberately lossy: Extreme and Severe both become `red`, because this domain
# has three levels. The original CAP value is preserved in provider_severity.
# `Unknown` maps to nothing, so it can never satisfy a policy tier.
SEVERITY_TO_ALERT_LEVEL = {
    "Extreme": "red",
    "Severe": "red",
    "Moderate": "orange",
    "Minor": "green",
}

# Authorized WMO OET event codes only. Anything absent is counted unsupported
# and skipped; no free-text headline or description is ever used to guess a
# hazard type.
#
# Deliberately NOT mapped, pending separate authorization:
#   OET-103  rising water level / flow  - hydrological infrastructure, not
#            meteorological flooding, so it is not treated as `flood`.
#   OET-100  high waves                 - marine, out of construction scope.
HAZARD_BY_EVENT_CODE = {
    "OET-079": "flood",
    "OET-098": "extreme_heat",
    "OET-170": "dust_storm",
}

MAX_FEED_ITEMS = 60
MAX_REFERENCE_DEPTH = 8
MAX_AREA_BLOCKS = 16
MAX_TITLE_LENGTH = 255


def _text(element, path):
    if element is None:
        return ""
    value = element.findtext(path, namespaces=NS)
    return (value or "").strip()


def parse_xml(body):
    """Parse provider XML with entity expansion refused.

    ``ElementTree`` never resolves external entities, so XXE is not reachable;
    rejecting a DTD outright also removes internal-entity expansion attacks.
    """

    if isinstance(body, bytes):
        head = body[:2048].lstrip()
        marker = b"<!DOCTYPE"
    else:
        head = body[:2048].lstrip()
        marker = "<!DOCTYPE"
    if head[:200].upper().startswith(marker.upper()) or marker.upper() in head.upper():
        raise MalformedProviderPayload("xml_doctype_rejected")
    try:
        return ET.fromstring(body)
    except ET.ParseError:
        raise MalformedProviderPayload("invalid_xml") from None


def cap_document_urls(feed_root):
    """Approved CAP document links from the RSS discovery index."""

    urls = []
    for item in feed_root.findall("./channel/item")[:MAX_FEED_ITEMS]:
        link = (item.findtext("link") or "").strip()
        # Only links on the approved host are ever fetched.
        if safe_source_url(link, PROVIDER):
            urls.append(link)
    return urls


def _severity_and_level(info):
    severity = _text(info, "cap:severity")
    if not severity:
        raise RejectedProviderRecord("severity_missing")
    alert_level = SEVERITY_TO_ALERT_LEVEL.get(severity)
    if alert_level is None:
        # `Unknown` or an unrecognized value: not actionable, never guessed.
        raise RejectedProviderRecord("severity_not_actionable")
    return severity, alert_level


def _event_code(info):
    for event_code in info.findall("cap:eventCode", NS):
        value = _text(event_code, "cap:value")
        if value:
            return value
    return ""


def _polygon(text):
    """CAP polygon text to one GeoJSON ring.

    CAP positions are ``latitude,longitude``; the canonical internal order is
    ``[longitude, latitude]``, so every pair is swapped here.
    """

    ring = []
    for pair in text.split():
        parts = pair.split(",")
        if len(parts) != 2:
            raise RejectedProviderRecord("polygon_malformed")
        try:
            latitude = float(parts[0])
            longitude = float(parts[1])
        except (TypeError, ValueError):
            raise RejectedProviderRecord("polygon_not_numeric") from None
        ring.append([longitude, latitude])
    if len(ring) < 3:
        raise RejectedProviderRecord("polygon_too_short")
    return ring


def _area_geometry(info):
    """Every CAP polygon as one MultiPolygon, or None when there is none.

    Disjoint areas are preserved as separate components and never merged. A
    malformed polygon rejects the whole alert rather than producing partial
    coverage that would silently under-warn.
    """

    polygons = []
    for area in info.findall("cap:area", NS)[:MAX_AREA_BLOCKS]:
        for polygon in area.findall("cap:polygon", NS):
            text = (polygon.text or "").strip()
            if not text:
                raise RejectedProviderRecord("polygon_empty")
            polygons.append([_polygon(text)])
    return polygons or None


def _reference_identifiers(info_root):
    """Identifiers referenced by this message.

    CAP references are ``sender,identifier,sent`` triples separated by
    whitespace. Only references from an approved sender are trusted, and no
    reference is ever dereferenced over the network.
    """

    raw = _text(info_root, "cap:references")
    identifiers = []
    for reference in raw.split():
        parts = reference.split(",")
        if len(parts) < 2:
            continue
        sender = parts[0].strip()
        identifier = parts[1].strip()
        if sender in APPROVED_SENDERS and identifier:
            identifiers.append(identifier)
    return identifiers


def resolve_root_identifier(identifier, parents):
    """Walk a CAP chain to its root Alert identifier.

    ``parents`` maps an identifier to the identifier it supersedes. Recursion
    is bounded and cycle-safe: a loop or an over-long chain resolves to the
    deepest identifier reached rather than looping or inventing an identity.
    """

    seen = {identifier}
    current = identifier
    for _ in range(MAX_REFERENCE_DEPTH):
        parent = parents.get(current)
        if not parent or parent in seen:
            break
        seen.add(parent)
        current = parent
    return current


def _normalize_alert(root, *, parents):
    identifier = _text(root, "cap:identifier")
    sender = _text(root, "cap:sender")
    status = _text(root, "cap:status")
    msg_type = _text(root, "cap:msgType")
    if not identifier:
        raise RejectedProviderRecord("identifier_missing")
    if sender not in APPROVED_SENDERS:
        raise RejectedProviderRecord("sender_not_approved")
    if status not in KNOWN_STATUSES:
        raise RejectedProviderRecord("status_unknown")
    if status != PRODUCTION_STATUS:
        raise RejectedProviderRecord("status_not_actual")
    if msg_type not in KNOWN_MSG_TYPES:
        raise RejectedProviderRecord("msgtype_unknown")
    if msg_type not in (MSG_TYPE_ALERT, MSG_TYPE_UPDATE, MSG_TYPE_CANCEL):
        raise RejectedProviderRecord("msgtype_not_supported")

    info = root.find("cap:info", NS)
    if info is None:
        raise RejectedProviderRecord("info_missing")

    hazard_type = HAZARD_BY_EVENT_CODE.get(_event_code(info))
    if hazard_type is None:
        raise RejectedProviderRecord("event_code_unsupported")

    sent = utc_datetime(_text(root, "cap:sent"), "sent", required=True)
    effective = utc_datetime(_text(info, "cap:effective"), "effective", required=False)
    onset = utc_datetime(_text(info, "cap:onset"), "onset", required=False)
    expires = utc_datetime(_text(info, "cap:expires"), "expires", required=False)

    # One logical hazard per warning chain: an Update or Cancel is stored
    # against the identifier of the Alert it ultimately supersedes.
    root_identifier = resolve_root_identifier(identifier, parents)

    if msg_type == MSG_TYPE_CANCEL:
        # Withdrawal flows through the existing provider_status semantics; the
        # human workflow decides what happens to any open alert.
        severity, alert_level = "", None
        provider_status = "withdrawn"
    else:
        severity, alert_level = _severity_and_level(info)
        provider_status = "active"

    area_polygons = _area_geometry(info)
    headline = bounded_text(_text(info, "cap:headline"), MAX_TITLE_LENGTH)
    event = bounded_text(_text(info, "cap:event"), MAX_TITLE_LENGTH)
    title = headline or event
    if not title:
        raise RejectedProviderRecord("title_missing")

    # Every identifier this chain is known to use. Recorded on ingestion so a
    # revision arriving after the original message has left the feed still
    # resolves to the same hazard.
    aliases = [root_identifier[:128], identifier[:128]]
    for referenced in _reference_identifiers(root):
        if referenced[:128] not in aliases:
            aliases.append(referenced[:128])

    return {
        "provider": PROVIDER,
        "provider_event_id": root_identifier[:128],
        "identity_aliases": tuple(aliases),
        # An Update or Cancel revises a warning that must already exist.
        "revision_of_existing": msg_type in (MSG_TYPE_UPDATE, MSG_TYPE_CANCEL),
        "hazard_type": hazard_type,
        "title": title,
        "alert_level": alert_level,
        "provider_severity": bounded_text(severity, 32),
        "occurred_at": onset or effective or sent,
        "provider_updated_at": sent,
        "valid_from": effective or onset,
        "valid_until": expires,
        "provider_status": provider_status,
        "area_polygons": area_polygons,
        "source_url": safe_source_url(_text(info, "cap:web"), PROVIDER),
        "payload": {
            "cap_identifier": identifier,
            "cap_msg_type": msg_type,
            "cap_status": status,
            "cap_event": event,
            "cap_event_code": _event_code(info),
            "cap_severity": severity,
            "cap_urgency": _text(info, "cap:urgency"),
            "cap_certainty": _text(info, "cap:certainty"),
            "cap_category": _text(info, "cap:category"),
            "cap_area_desc": bounded_text(_text(info, "cap:areaDesc"), 200),
            "cap_language": _text(info, "cap:language"),
        },
    }


def normalize_documents(documents):
    """Translate fetched CAP documents into a ProviderBatch.

    ``documents`` is an iterable of parsed CAP roots. The whole batch is read
    once to build the reference map, so an Update is attributed to the Alert it
    supersedes even when both arrive in the same poll.
    """

    from apps.safety.services import NormalizedHazardEvent

    batch = ProviderBatch(provider=PROVIDER)
    roots = list(documents)[:MAX_FEED_ITEMS]
    batch.records_received = len(roots)

    parents = {}
    for root in roots:
        identifier = _text(root, "cap:identifier")
        sender = _text(root, "cap:sender")
        if not identifier or sender not in APPROVED_SENDERS:
            continue
        for referenced in _reference_identifiers(root):
            if referenced != identifier:
                parents[identifier] = referenced
                break

    for root in roots:
        try:
            values = _with_reference_point(_normalize_alert(root, parents=parents))
        except RejectedProviderRecord as exc:
            if str(exc) in ("event_code_unsupported", "severity_not_actionable"):
                batch.records_unsupported += 1
            else:
                batch.records_malformed += 1
            continue
        batch.events.append(NormalizedHazardEvent(**values))
    return batch


def _with_reference_point(values):
    """Attach the reference coordinate the existing schema requires.

    ``latitude``/``longitude`` are a display and audit reference only. Matching
    uses the authoritative polygon: this point is never used to decide which
    projects are affected, and no radius is derived from it.
    """

    area = values.get("area_polygons")
    if area:
        first_ring = area[0][0]
        longitudes = [position[0] for position in first_ring]
        latitudes = [position[1] for position in first_ring]
        values["latitude"] = sum(latitudes) / len(latitudes)
        values["longitude"] = sum(longitudes) / len(longitudes)
    else:
        raise RejectedProviderRecord("area_missing")
    return values


class MhewsWarningProvider:
    code = PROVIDER

    def enabled(self):
        return bool(settings.SAFETY_WEATHER_ENABLED)

    def fetch(self):
        feed = parse_xml(
            fetch_body(
                settings.SAFETY_MHEWS_FEED_URL,
                allowed_hosts=ALLOWED_HOSTS,
                timeout_seconds=settings.SAFETY_PROVIDER_TIMEOUT_SECONDS,
                max_bytes=settings.SAFETY_PROVIDER_MAX_BYTES,
                accept="application/rss+xml, application/xml, text/xml",
                content_type_token="xml",
            )
        )
        documents = []
        for url in cap_document_urls(feed):
            documents.append(
                parse_xml(
                    fetch_body(
                        url,
                        allowed_hosts=ALLOWED_HOSTS,
                        timeout_seconds=settings.SAFETY_PROVIDER_TIMEOUT_SECONDS,
                        max_bytes=settings.SAFETY_PROVIDER_MAX_BYTES,
                        accept="application/xml, text/xml",
                        content_type_token="xml",
                    )
                )
            )
        return normalize_documents(documents)
