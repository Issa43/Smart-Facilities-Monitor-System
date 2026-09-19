# Camera Integration Boundary

## Current implementation

SFLMS currently stores a facility-scoped Camera registry with status and
last-seen metadata. Camera pages represent persisted registry/status data;
they are not live streams.

AI/CV processing is external to Django. SFLMS does not capture frames, open
RTSP streams, run inference, or store raw detections.

## Machine access

External AI services use dedicated machine credentials and explicit Camera
scopes. A successful credential check does not grant global camera or Facility
access. Ingestion services resolve an authorized Camera through
the shared scope service and derive Facility ownership from `Camera.facility`.

Credentials must never be assigned a human role or use human JWT login.

## Final event ingestion

`POST /api/v1/camera-events/` accepts final confirmed events only through the
dedicated machine authenticator. Facility is derived from the scoped Camera.
The database identity `(ingestion_credential, source_event_id)` prevents retry
duplicates. A tracked lifecycle is POSTed once and then PATCHed; per-frame
records are not created.

On the wire, external services submit `camera_id` and, for fire, smoke, and
intrusion, `class`. Django maps these to its existing internal `camera` and
`object_class` fields. The internal names are not accepted as alternate POST
fields, so the executable endpoint and generated OpenAPI schema define one
authoritative external contract.

Fire, smoke, intrusion, unauthorized vehicle, and tamper events atomically
create exactly one human-actionable `SecurityAlert`. Authorized vehicle events
remain recorded without an alert. CameraEvent creation never creates an
Incident; Incident conversion remains a reviewed SecurityAlert workflow.

The external service places required JPEG snapshots (optional only for tamper) in protected storage under
`security/camera-events/{facility_uuid}/{camera_uuid}/`. Django validates the
storage-relative key and content and exposes only an authorized download route.

## Current configuration API

The backend stores and serves camera-scoped ROIs, ROI restricted schedules,
one virtual line per camera, per-camera active model assignments, and the
authoritative authorized-vehicle registry. AIKey reads are limited to the
credential's active camera scopes; human configuration is Super Admin-only.

ROI polygons and virtual lines use unmodified, finite, non-negative pixel
coordinates matching the CameraEvent coordinate convention. Schedule
timezones use IANA names, weekdays use `0=Monday` through `6=Sunday`, and an
overnight range belongs to its listed local start day and ends the next day.

These records describe external processing configuration. Soft-disable and
updates do not rewrite historical CameraEvents. The backend FCM path and the
human frontend event/configuration contracts are implemented; physical-device
FCM receipt and all AI/CV inference remain outside this release gate.

## Live security delivery

Committed final CameraEvents are distributed best-effort through
`/ws/security/events/` to authorized human dashboards. A linked SecurityAlert
is included in the same creation message, avoiding a duplicate UI creation
event. Authorized vehicle events are also delivered but contain no alert.

Human SecurityAlert review, dismissal, and conversion emit a bounded
`security.alert.updated` message after commit. Continuous CameraEvent PATCH
does not broadcast. REST remains authoritative for initial/reconnect state.
The WebSocket never carries frames, raw detections, storage keys, or snapshot
content and never accepts AIKey credentials.

## Deployment requirement

Machine credentials must be transmitted over TLS. Reverse-proxy TLS and
optional mTLS are deployment concerns; application-level credential and Camera
scope validation remain mandatory.
