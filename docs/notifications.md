# Notifications

## Purpose
Explains how the system tells users things happened — the combination of
a durable database record and a real-time push, and how the two stay
consistent.

## Scope
Notification generation, storage, and real-time delivery. What triggers a
notification (an Alert, a maintenance due date...) is owned by each
originating domain (`ai-engine.md`, `business-domain.md`); this document
covers the notification mechanism itself.

## Architecture

### Dual-path design
```
Event happens (Alert created, Maintenance due, Material low stock...)
    │
    ▼
Notification row created (DB write — always happens, source of history)
    │
    ▼
Channels broadcast (WebSocket push — best-effort, real-time)
    │
    ▼
Frontend: if connected, receives instantly; if not, sees it on next
          GET /api/notifications/ (unread count + list) — no event is
          ever lost because delivery isn't connection-dependent
```
The DB write is never skipped even if no one is connected to receive the
broadcast — this is why `Notification` exists as a table at all rather
than being a pure WebSocket-only ephemeral event.

### Targeting: personal vs. facility broadcast
`Notification.user` (nullable) targets one person. `Notification.facility`
(nullable, added specifically for this purpose) targets everyone assigned
to that Facility — e.g., a Security Alert notifies every
`FacilityAssignment` row's user for that facility, not one hardcoded
recipient. A notification is either personal (`user` set, `facility`
null) or a facility broadcast (`facility` set, `user` null) — never
ambiguously both undefined.

### WebSocket layer (Phase 7, specified not yet implemented)
```
apps/notifications/consumers.py — NotificationConsumer (Channels)
apps/notifications/routing.py   — ws/notifications/ route
apps/notifications/middleware.py — JWTAuthMiddleware (see authentication.md)

Group naming: user_<user_id> for personal, facility_<facility_id> for
broadcast — a client subscribes to their own user group on connect, plus
one group per Facility they're assigned to (resolved server-side from
their Assignment rows, not client-supplied).
```
Redis is the Channels layer backend (`CHANNEL_LAYERS`, added in Phase 7)
— the same Redis instance already used for Celery (see
`system-architecture.md`).

## Business Rules
- A notification's `is_read` state is per-recipient — for a facility
  broadcast, this means read-state should logically be per-(notification,
  user) pair, not a single flag on the notification row. **Open design
  question, not yet resolved** — see Future Evolution.
- `related_module`/`related_id` let the frontend deep-link to the source
  record (an Incident, a MaintenanceOrder...) without the notification
  needing a typed FK to every possible source model (same pattern
  rationale as Attachments — see ADR-0013).

## Technical Notes
Priority (`normal`/`high`/`critical`) is stored per-notification and is
expected to drive frontend styling (e.g., critical = persistent banner,
not just a toast) — this is a frontend concern documented here only
because the field's *meaning* is a shared contract between backend and
frontend.

## Current Implementation
Not implemented. `apps/notifications/` is a placeholder.

## Future Evolution
- **Per-recipient read state for broadcasts** — the current schema
  (`is_read` as a single column) works cleanly for personal notifications
  but is ambiguous for facility broadcasts (5 assigned users, has each of
  them read it?). Two options to decide between at implementation time:
  (a) fan out a personal `Notification` row per assigned user at creation
  time (simplest, more rows), or (b) a separate
  `NotificationReadReceipt(notification, user, read_at)` join table
  (fewer rows, more query complexity). **Not decided — flagged explicitly
  so Phase 7 implementation doesn't silently pick one without recording
  the choice as an ADR.**
- Push notifications to mobile/browser (outside WebSocket, e.g. web push)
  — out of current scope, candidate for `future-roadmap.md`.

## Important Decisions
Notification is always persisted before/regardless of broadcast delivery
(documented above) — not yet its own ADR, candidate if questioned later.

## Developer Notes
Never trigger a Channels broadcast without first writing the
`Notification` row in the same operation (ideally same DB transaction) —
broadcast-only "fire and forget" notifications would silently violate the
durability guarantee this whole design exists to provide.

## Related Components
`ai-engine.md`, `authentication.md` (WebSocket JWT), `system-architecture.md`.

## Files Involved
`apps/notifications/*` (not yet created).

## Dependencies
`glossary.md`, `authentication.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
The rule that a DB write always happens regardless of broadcast success —
this is the reliability guarantee the entire notification system rests on.

## Future Improvements
Resolve the per-recipient read-state design question above before or
during Phase 7 — write it up as an ADR once decided, don't leave it as a
silent implementation detail.
