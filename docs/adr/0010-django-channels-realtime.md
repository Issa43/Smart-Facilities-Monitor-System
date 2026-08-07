# 0010. Django Channels for Real-Time Delivery

## Status
Accepted

## Context
Safety-critical events (fire, smoke, intrusion, critical faults) require
real-time delivery to Security Officers and Operations Managers — a
polling-only notification design was explicitly rejected as insufficient
for these event types, though polling remains a valid fallback for
offline/disconnected clients.

## Decision
Django Channels, with Redis as the channel layer backend (reusing the
same Redis instance already used by Celery, see ADR-0009), provides
WebSocket-based real-time push. Every notification is still persisted to
the database first (see `notifications.md`) — the WebSocket broadcast is
additive delivery, never the sole record of an event.

## Consequences
- Users connected via WebSocket receive events within the delivery
  latency of the Channels/Redis pub-sub mechanism, not a polling
  interval.
- Requires a custom JWT-based Channels middleware (Phase 7,
  `authentication.md` §WebSocket authentication) since browsers cannot
  attach custom headers to a WebSocket handshake — token passed as a
  query parameter instead.
- `ASGI_APPLICATION` and `config/asgi.py` exist from Phase 1 specifically
  so this integration requires no restructuring later (verified in
  `PHASE1_FORWARD_COMPATIBILITY_AUDIT.md` §4).
- The per-recipient read-state question for facility-broadcast
  notifications (fan-out rows vs. read-receipt table) remains open and
  must be resolved before/during Phase 7 implementation (see
  `notifications.md` §Future Evolution) — this ADR does not itself
  resolve that question.

## Alternatives Considered
- **Long-polling / short-interval polling only**: rejected — explicitly
  insufficient for safety-critical event latency requirements.
- **A separate real-time service** (e.g., a standalone WebSocket server
  outside Django): rejected — Channels integrates directly with the
  existing Django/DRF authentication and app structure, avoiding a
  second service for what is, at current scale, a well-supported
  in-process capability.

## Related
`notifications.md`. `authentication.md`. `system-architecture.md`.
ADR-0009.
