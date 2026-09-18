# 0010. Django Channels for Real-Time Delivery

## Status
Accepted

## Context
Safety-critical camera events require real-time delivery to Security Officers
and Super Admins — a
polling-only notification design was explicitly rejected as insufficient
for these event types, though polling remains a valid fallback for
offline/disconnected clients.

Operations Managers remain outside the current realtime permission model.
Their separate Incident transfer workflow does not grant Security Officer
stream access or arbitrary security mutations.

## Decision
Django Channels, with Redis as the channel layer backend (reusing the
same Redis instance already used by Celery, see ADR-0009), provides
WebSocket-based real-time delivery of committed CameraEvent and SecurityAlert
domain updates. This best-effort live path is independent from the durable
Notification/Celery/FCM path. The persisted CameraEvent or
SecurityAlert remains authoritative even if no WebSocket client is connected.

## Consequences
- Users connected via WebSocket receive events within the delivery
  latency of the Channels/Redis pub-sub mechanism, not a polling
  interval.
- Requires custom JWT-based Channels middleware. Browsers offer the literal
  `sflms.jwt` and the short-lived access token as WebSocket subprotocol values;
  the server validates the token and accepts only `sflms.jwt`. Query-string
  tokens and AIKey machine credentials are rejected.
- `ASGI_APPLICATION` and `config/asgi.py` exist from Phase 1 specifically
  so this integration requires no restructuring later (verified in
  `PHASE1_FORWARD_COMPATIBILITY_AUDIT.md` §4).
- WebSocket clients use REST for initial state; the live channel provides no
  replay or notification read-state semantics.

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
