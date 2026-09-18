# Notifications

## Purpose
Explains the independent mechanisms used for live security-event delivery and
durable, recipient-specific notifications.

## Scope
Notification generation and storage, plus the separate security-event
WebSocket contract. What triggers a durable notification (an Alert, a
maintenance due date...) is owned by each originating domain
(`ai-engine.md`, `business-domain.md`).

## Architecture

### Independent delivery paths

Live dashboard delivery and durable user notification are separate consumers
of persisted security-domain state. A WebSocket broadcast does not create a
`Notification`, and a `Notification` is not required merely to permit a live
broadcast.

#### Live realtime path

```
CameraEvent / SecurityAlert committed
    -> Channels
    -> authorized WebSocket dashboard (best-effort)
```

This path distributes only already-persisted final domain events. It is
ephemeral, has no replay guarantee, and is not a substitute for REST initial
state. Missing a WebSocket event does not imply that the CameraEvent or
SecurityAlert was lost.

#### Durable notification path

```text
SecurityAlert committed
    -> durable Notification
    -> Celery
    -> FCM
    -> mobile push
```

This path owns persistent/mobile notification delivery. Batch 5 implements it
for eligible CameraEvent-originated SecurityAlerts. Other domains continue to
create durable Notifications without automatically using FCM.

### Current Notification model

Every `Notification` row belongs to exactly one `recipient`; there is no
`Notification.user` or `Notification.facility` field. When a domain workflow
targets multiple eligible users, the notification service fans out one durable
row per recipient. Consequently, read state is individual and unambiguous:
`read_at=null` means unread and a timestamp means that recipient has read the
notification. The derived API property `is_read` is not a database column.

The persisted fields are:

- `id` (UUID primary key), `created_at`, `updated_at`, `created_by`, and
  `is_active` inherited from `BaseModel`;
- `recipient` (required User foreign key);
- `title`, `body`, `category`, and `tone`;
- optional `href`, `source_type`, and `source_id` linkage;
- optional unique `deduplication_key`;
- optional `read_at` timestamp.

Current categories are `project`, `material`, `maintenance`, `security`, and
`system`. Current tones are `neutral`, `info`, `success`, `warning`, and
`critical`.

### Security-event WebSocket layer
```
apps/security/consumers.py       — SecurityEventConsumer
apps/security/routing.py         — ws/security/events/ route
apps/authentication/websocket.py — JWT subprotocol authentication

Group membership and recipient selection are server-owned. Clients cannot
subscribe to arbitrary facilities or issue domain mutations through the
socket.
```
Redis is the Channels layer backend (`CHANNEL_LAYERS`, added in Phase 7)
— the same Redis instance already used for Celery (see
`system-architecture.md`).

### Live security protocol

The only route is `/ws/security/events/`. It is server-to-client only and
does not accept subscriptions or domain mutations. Successful connection
returns:

```json
{"type": "security.connection.ready", "version": 1}
```

New final events use this stable envelope:

```json
{
  "type": "security.camera_event.created",
  "version": 1,
  "event": {
    "id": "uuid",
    "event_type": "fire_alert",
    "camera_id": "uuid",
    "facility_id": "uuid",
    "roi_id": null,
    "track_id": null,
    "object_class": "fire",
    "confidence": "0.875000",
    "detected_at": "ISO-8601 datetime",
    "confirmed_at": null,
    "duration_seconds": null,
    "authorized": null,
    "direction": null,
    "plate_number": null,
    "tamper_type": null,
    "security_alert_id": "uuid",
    "status": "new",
    "snapshot": {
      "available": false,
      "download_path": null
    }
  },
  "security_alert": {
    "id": "uuid",
    "event_id": "uuid",
    "facility_id": "uuid",
    "camera_id": "uuid",
    "alert_type": "fire",
    "severity": "critical",
    "status": "new",
    "is_false_positive": false,
    "created_at": "ISO-8601 datetime",
    "updated_at": "ISO-8601 datetime"
  }
}
```

Authorized vehicle entry/exit uses the same event envelope with
`security_alert=null`. Human review, dismissal/false-positive, and conversion
produce `security.alert.updated` with the bounded alert object. CameraEvent
PATCH produces no WebSocket message. A snapshot reference is only the relative
authenticated CameraEvent download route; storage keys, public URLs, bytes,
and Base64 are never sent.

Each connected eligible human joins only an internal per-user group. At
broadcast time Django makes one recipient query for active Super Admins plus
active Security Officers with `alert.view` and a current active assignment to
the event Facility. This applies assignment/account changes to newly emitted
events without a database authorization query per connected socket. Group
names and authorized Facility lists are never returned to the client.

Creation broadcasts are registered only for the transaction that created the
CameraEvent. Idempotent retries, conflicting retries, rollbacks, and PATCH do
not register another creation message. Channels delivery failures are logged
after commit and cannot roll back persisted domain state.

## Business Rules
- Each row has one required `recipient` and its own `read_at`; no facility-wide
  read-state exists.
- `source_type`/`source_id` identify an optional originating record without a
  typed foreign key to every possible source model. `href` provides the
  recipient-specific frontend destination.
- Durable fan-out is idempotent when a `deduplication_key` is supplied; the
  service prefixes that key with the recipient UUID.

## Technical Notes
`tone` (`neutral`/`info`/`success`/`warning`/`critical`) is stored per
notification and may drive frontend presentation. It is distinct from a
SecurityAlert's server-owned severity.

## Current Implementation

The `apps/notifications` application contains the models, persistence
services, Celery tasks, migrations, and tests. Its REST serializers, views,
and routes live in `api/v1/platform/`. The API lists only the authenticated
user's rows and provides per-row `read`, `read-all`, and preference operations.

Implemented Celery jobs create recipient-specific durable reminders for
project completion milestones, overdue work orders, and critical security
alerts. Eligible CameraEvent-originated SecurityAlerts now create their
recipient-specific rows in the same transaction, then create per-device
`PushDelivery` rows and enqueue FCM after commit. The security-event Channels
boundary remains separate in `apps/security`.

### Mobile device contract

All routes require a human JWT; AIKey and anonymous callers are rejected.

| Method | Route | Behavior |
|---|---|---|
| `GET`/`POST` | `/api/v1/notifications/devices/` | List the current user's registrations or idempotently register a token |
| `GET`/`PATCH`/`DELETE` | `/api/v1/notifications/devices/{id}/` | Read/update or soft-disable only the current user's device |

`POST` and `PATCH` accept `token` (write-only) and `platform` (`android` or
`ios`). Responses never contain the token. Registering the same token for the
same user reactivates and refreshes it; another user cannot claim or manage it.
`DELETE` disables the registration without deleting delivery history.

The FCM notification contains a short Arabic title/body. Its data payload is:

```json
{
  "type": "security_alert",
  "alert_id": "uuid",
  "event_type": "fire_alert",
  "severity": "critical",
  "facility_id": "uuid",
  "camera_id": "uuid"
}
```

Mobile clients use `alert_id` with the authenticated SecurityAlert REST flow.
No snapshot key, public snapshot URL, token, credential, or raw detection is
sent through FCM.

### Push eligibility and delivery state

Initial `fire_alert`, `smoke_alert`, `intrusion_alert`, `tamper_alert`, and
unauthorized `vehicle_entry`/`vehicle_exit` events are eligible. Authorized
vehicle events, CameraEvent PATCH, tracking updates, reads, WebSocket events,
and manual/generic mutations do not enqueue push.

Recipients are active Super Admins and active Security Officers who have
`alert.view`, an active Security Officer assignment to the Facility, and have
not disabled the existing `critical_alerts` notification preference. Eligibility
is checked again immediately before FCM; losing an assignment disables only
that delivery and does not rewrite the durable Notification.

`PushDelivery` is unique per Notification/device and stores `queued`,
`processing`, `sent`, `failed`, `invalid_token`, or `skipped` separately from
`Notification.read_at`. Transient provider/network errors use at most five
retries with bounded exponential backoff. An FCM unregistered-token response
disables that device only. A recovery task republishes queued work and releases
worker claims stale for ten minutes.

FCM cannot guarantee exactly-once delivery if the provider accepts a message
and the worker fails before recording the returned message ID. Database claims,
terminal delivery states, and unique constraints minimize duplicates; the
documented guarantee is durable at-least-once processing, not exactly-once
mobile display.

## Future Evolution
- Additional durable Notification categories may opt into mobile delivery only
  through a separately approved policy; Batch 5 enables SecurityAlerts only.
- If a facility-addressed durable record is ever proposed instead of the
  current per-recipient fan-out, that would be a future schema redesign and
  would require an explicit ADR. It is not current behavior.

## Important Decisions

Batch 4 supersedes the earlier rule that every Channels broadcast requires a
Notification row. Live dashboard delivery and durable/mobile notifications
are intentionally independent paths rooted in committed domain state.

## Developer Notes

Never broadcast an uncommitted CameraEvent or SecurityAlert. Register live
delivery through `transaction.on_commit()`. Do not create a Notification only
to enable a WebSocket broadcast.

## Related Components
`ai-engine.md`, `authentication.md` (WebSocket JWT), `system-architecture.md`.

## Files Involved
`apps/notifications/models.py`, `services.py`, `tasks.py`, migrations and
tests; `api/v1/platform/serializers.py`, `views.py`, and `urls.py`; and the
independent `apps/security/consumers.py`, `routing.py`, and `realtime.py`.

## Dependencies
`glossary.md`, `authentication.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation

Durable notifications remain persisted independently of delivery success.
Live WebSocket delivery remains best-effort and must originate only from
successfully committed domain state.

## Future Improvements
Add provider observability dashboards without exposing registration tokens or
creating per-attempt AuditLog noise.
