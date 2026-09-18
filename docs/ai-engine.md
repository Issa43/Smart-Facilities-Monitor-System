# External AI Integration

## Scope boundary

AI/CV models run outside Django. SFLMS does not implement or host inference,
OpenCV capture, YOLO, OCR, tracking, ByteTrack, temporal filtering, model
training, datasets, thresholds, or weights. Raw frames and raw per-frame
detections must not be stored by this integration.

The future integration contract is:

```text
External AI service -> authenticated REST -> Django -> database
```

Django accepts final confirmed events through the Batch 2 `CameraEvent`
contract. `apps/ai_engine/` remains a placeholder and is not evidence of
in-process AI functionality.

## Machine authentication (Batch 1)

External AI services authenticate with dedicated machine credentials. They do
not use human JWTs and do not impersonate Super Admin, Security Officer,
Operations Manager, or Construction Manager.

Each credential has:

- a roleless, non-interactive User principal with an unusable password;
- a public `key_id` and a securely hashed secret;
- expiration and revocation state;
- explicit active Camera scopes.

The wire format is:

```http
Authorization: AIKey <key_id>:<secret>
```

The plaintext secret is returned only when a Super Admin creates or rotates a
credential. It is never stored or returned by list/detail/revoke operations.
TLS is required in deployment.

Authentication alone grants no camera access. Event ingestion calls the shared
camera-scope authorization service and derives the Facility from
`Camera.facility`; it never trusts a client-supplied Facility.

## Final event ingestion (Batch 2)

`CameraEvent` is the durable final-event record. Machine-authenticated POST is
idempotent on `(ingestion_credential, source_event_id)`. An identical retry
returns the existing event; a conflicting retry is rejected. Continuous
tracked observations PATCH the same event and may update only confidence,
bounds, duration, confirmation time, or protected snapshot. PATCH never
creates another alert, notification, Incident, or semantic creation audit.

Alertable events create one `SecurityAlert` in the same database transaction.
Authorized vehicle entry/exit remains a CameraEvent without an alert.
`SecurityAlert` owns human review, false-positive, dismissal, and Incident
conversion state; `CameraEvent.status` is a read projection rather than a
second persisted workflow status.

The authoritative external POST contract uses `camera_id` for the scoped
Camera and `class` for the classified object. The serializer maps those wire
names to the existing internal `camera` and `object_class` fields. Internal
field names are not accepted as alternate POST aliases, and `source_event_id`
remains mandatory for idempotency.

Snapshots are pre-placed by the external service under
`security/camera-events/{facility_uuid}/{camera_uuid}/{opaque_filename}.jpg`.
Django verifies the protected object, prefix, extension, and image signature.
Storage keys and public media URLs are not serialized.

## Current configuration contracts (Batch 3)

Django now owns the current configuration consumed by external AI services:

- active ROIs are camera-owned polygons expressed as ordered pixel-space
  `{x, y}` points; coordinates are finite and non-negative, polygons have at
  least three distinct points, and Django performs no coordinate transforms;
- each ROI may have one current restricted schedule. `timezone_name` is an
  IANA identifier, `days_of_week` uses `0=Monday` through `6=Sunday`, and each
  listed day denotes the local start day. A range such as `22:00` to `06:00`
  continues into the following local day. Always-restricted schedules carry
  no times or days;
- each camera may have one current virtual line, represented by two distinct
  finite, non-negative pixel-space endpoints. Crossing and direction remain
  external responsibilities;
- the authorized-vehicle registry stores a minimally normalized plate (trimmed
  and uppercased), responsible name, optional inclusive expiration date, and
  active state. A plate is currently authorized only while active and when
  `expires_on` is null or is today/future in Django's configured local date;
- a camera may independently enable any combination of `fire_smoke`,
  `intrusion`, `anpr`, and `tamper`.

AIKey credentials can read only active configuration for active cameras and
facilities within their explicit scopes. Machine access is read-only. Human
configuration reads and mutations use JWT and are Super Admin-only because
the existing human RBAC vocabulary contains no camera-configuration grant.
Authorized-vehicle machine lookup is available only to a credential with an
ANPR-enabled camera in its scope and omits responsible-person data.

Configuration is current/future processing state. Disable is soft, and
configuration changes never rewrite historical CameraEvents. A supplied
`CameraEvent.roi_id` must resolve to an active ROI belonging to the event's
authorized camera; tamper and vehicle events do not accept ROI.

The backend provides configuration and final-event ingestion contracts. AI
inference remains external to Django.

Implemented downstream consumers remain server-owned and independent:

- Channels/WebSocket live event delivery;
- durable Notification/Celery/FCM delivery for eligible SecurityAlerts.

AI models, inference, streams, frames, and raw detections remain outside this
repository.

## Credential administration

Super Admin-only routes are mounted at:

```text
/api/v1/admin/ai-ingestion-credentials/
```

Supported operations are create, list, detail, rotate, revoke, add Camera
scope, and deactivate Camera scope. Semantic audit actions never contain a
secret, secret hash, or Authorization header.

## Related components

- `authentication.md`
- `camera-processing.md`
- `api-specification.md`
- `apps/security/models.py`
- `apps/security/machine_credentials.py`
- `apps/security/authentication.py`
