# Future Roadmap

## Purpose
Ideas and capabilities beyond the current Phase 1–10 plan
(`implementation-phases.md`) — post-production evolution, not committed
work. Distinct from `known-limitations.md` (current gaps with a scheduled
resolution) — everything here is speculative and unscheduled.

## Scope
Post-production and long-horizon ideas across every domain.

## Architecture
N/A.

## Business Rules
N/A.

## Technical Notes

### AI Engine
- License plate recognition raising active `SecurityAlert`s against an
  authorized-vehicle allowlist (currently `VehicleRecognition` is passive
  logging only — see `ai-engine.md` §Future Evolution).
- Additional detection types beyond the initial set (Fire, Smoke,
  Intrusion, Unauthorized Presence, Vehicle) as facility needs are
  identified — the `AIModel`/`CameraDetectionEvent` schema already
  supports adding a new `detection_type` without a structural change.
- On-camera edge inference (moving YOLO closer to the camera rather than
  centralizing in `celery_worker`) if network bandwidth or latency ever
  becomes a constraint at scale — a significant architecture change,
  would need its own ADR if pursued.

### Notifications
- Web push / mobile push notifications (outside the WebSocket channel)
  for users not actively viewing the frontend.
- Notification preferences per user (which event types trigger a push
  vs. in-app-only).

### Reporting
- Scheduled/recurring reports via Celery Beat (e.g., automatic weekly
  security summary) — see `reporting.md` §Future Improvements.
- Dashboard-style live analytics (as distinct from generated report
  files) — not currently in scope; would likely warrant its own document
  if pursued given the architectural surface area (real-time aggregation,
  possibly a separate read-optimized data path).

### Infrastructure
- Cloud migration (see `system-architecture.md` §Future cloud migration)
  — containers are already designed to map cleanly to
  ECS/Kubernetes-style orchestration; the storage abstraction
  (`backend-architecture.md` §Storage) already anticipates an S3-compatible
  swap for `MEDIA_ROOT`.
- Splitting Redis's three roles (Celery broker, result backend, Channels
  layer) into separate instances if load ever contends
  (`system-architecture.md`, `performance.md`).
- Extracting `ai_engine`'s inference pipeline into a genuinely separate
  service (the current in-Django-via-Celery design's natural extraction
  point, per ADR-0008) if GPU resource isolation or independent scaling
  ever requires it.

### Access Control
- Multi-facility bulk assignment tooling (assigning a user to many
  Facilities/Projects at once) if the number of Facilities grows large
  enough that one-at-a-time `FacilityAssignment` creation becomes an
  operational burden.
- Reconsidering the fixed-4-role model only if a genuinely new
  organizational role emerges from real usage — not speculatively
  designed for in advance (see ADR-0006's reasoning).

## Current Implementation
None of the above — all speculative.

## Future Evolution
Ideas move from this document into `implementation-phases.md` (as a new,
scheduled phase) only when there's a concrete trigger (a real
requirement, a measured bottleneck) — not proactively.

## Important Decisions
None yet — nothing here is committed.

## Developer Notes
Do not build toward anything in this document speculatively — it exists
so ideas aren't lost, not as a backlog to pull from without a real
trigger.

## Related Components
`implementation-phases.md`, `known-limitations.md`.

## Files Involved
None.

## Dependencies
None.

## Things That MUST NEVER Be Changed Without Updating Documentation
N/A.

## Future Improvements
N/A — this document is itself the future-improvements list.
