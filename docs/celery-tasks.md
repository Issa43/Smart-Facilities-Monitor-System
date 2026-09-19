# Celery Tasks

## Purpose
The single authoritative registry of every Celery task in the system —
cross-cutting across `ai_engine`, `maintenance`, `reports`, so no task
gets defined, renamed, or duplicated without this document knowing about
it.

## Scope
Task definitions: name, trigger, queue, retry policy, idempotency. Task
*implementation* logic lives in each app's `services.py` (tasks
orchestrate, services execute — see `coding-patterns.md`); this document
is the registry, not the implementation.

## Architecture

### Queue strategy
Two logical queues from the start (configured via Celery routing, not yet
implemented — see Current Implementation):
- `default` — general-purpose tasks (reports, predictions, notifications).
- `ai_processing` — camera frame capture + YOLO inference, kept separate
  so a backlog of AI work never starves report generation or vice versa
  (see `performance.md` §Known future bottlenecks).

### Task registry

| Task | App | Trigger | Queue | Retry policy | Idempotent? |
|---|---|---|---|---|---|
| `sflms.infrastructure_health` | `config` | Manual/monitoring verification | `default` | None; returns immediately without dependencies or side effects | Yes |
| `capture_camera_frame` | `ai_engine` | Recurring, per active camera (scheduled via `celery_beat` or a long-running loop task — TBD, see Future Evolution) | `ai_processing` | 3 retries, 10s backoff, on transient RTSP connection errors | Yes — capturing "a" frame has no meaningful duplicate-effect risk |
| `process_frame` (YOLO inference) | `ai_engine` | Enqueued by `capture_camera_frame` | `ai_processing` | 3 retries, 10s backoff | Yes — re-running inference on the same frame produces the same `CameraDetectionEvent`-worthy result; guarded by not double-enqueuing the same frame reference |
| `generate_material_prediction` | `materials` | `celery_beat`, daily | `default` | 2 retries, 60s backoff | Yes — recomputing a prediction for a Material simply creates a newer `MaterialPrediction` row |
| `generate_asset_health_prediction` | `assets` | `celery_beat`, daily | `default` | 2 retries, 60s backoff | Yes — same reasoning as above |
| `generate_report` | `reports` | User action (`POST /api/reports/generate/`) | `default` | 1 retry, then `Report.status="failed"` (no silent infinite retry on a user-triggered action) | No — re-running creates a second `Report` row by design (user can regenerate) |
| `notifications.notify_project_completion_reminders` | `notifications` | Celery Beat, daily | `default` | Up to 5 retries for transient infrastructure errors, exponential backoff with jitter | Yes — per-recipient milestone deduplication key |
| `notifications.notify_overdue_work_orders` | `notifications` | Celery Beat, daily | `default` | Up to 5 retries for transient infrastructure errors, exponential backoff with jitter | Yes — per-recipient/order/day deduplication |
| `notifications.notify_critical_security_alerts` | `notifications` | Celery Beat, every 60 seconds | `default` | Up to 5 retries for transient infrastructure errors, exponential backoff with jitter | Yes — per-recipient SecurityAlert deduplication key |
| `notifications.deliver_push_notification` | `notifications` | Post-commit eligible SecurityAlert fan-out or recovery | `default` | Up to 5 transient FCM/network retries with bounded exponential backoff | One delivery row per Notification/device; terminal states are not resent |
| `notifications.recover_queued_push_deliveries` | `notifications` | Celery Beat, every 60 seconds | `default` | Next beat retries broker publication; releases claims stale for 10 minutes | Yes — reuses the unique delivery row |
| `safety.poll_usgs_earthquakes` | `safety` | Celery Beat, every `SAFETY_USGS_POLL_SECONDS` (default 300 s, message expires after one interval) | `default` | Up to `SAFETY_PROVIDER_MAX_RETRIES` (default 2, max 3) retries only for retryable network/timeout/5xx failures, 30–100 s backoff; malformed payloads, 4xx, and disabled states are not retried; HTTP 429 sets a cache backoff of up to 1 hour | Yes — `HazardEvent` unique per provider event id, `ProjectSafetyAlert` unique per project/event, notification deduplication keys; a cache lock skips overlapping polls; exits before any network call unless both alerting switches are on |
| `safety.poll_gdacs_events` | `safety` | Celery Beat, every `SAFETY_GDACS_POLL_SECONDS` (default 900 s, message expires after one interval) | `default` | Same bounded policy as USGS, backoff 30–300 s | Yes — same guarantees; while USGS polling is enabled, GDACS earthquakes are skipped before ingestion (counted as deferred to USGS) so earthquakes are never duplicated |
| `safety.poll_mhews_warnings` | `safety` | Celery Beat, every `SAFETY_MHEWS_POLL_SECONDS` (default 900 s, message expires after one interval) | `default` | Same bounded policy as USGS/GDACS | Yes — disabled by default behind `SAFETY_WEATHER_ENABLED` and exits before any request while off; CAP Updates resolve to the root Alert so a warning chain stays one `HazardEvent`; a cache lock skips overlapping polls |
| `safety.deliver_telegram_message` | `safety` | Post-commit, only after a human records a decision on a safety alert (`decide_alert_action` → `actioned`). No Beat entry — nothing schedules it | `default` | Up to `SAFETY_TELEGRAM_MAX_RETRIES` (default 3, max 5) for `429`, `5xx`, timeout, and connection failures, with bounded backoff honoring `retry_after`; invalid token, invalid chat, and other `4xx` fail permanently | Yes — one delivery row per `(alert, recipient, event_key)`; terminal rows are never resent, and a claim stale for 10 minutes is reclaimed inside the task |
| `check_maintenance_calendar` | `maintenance` | `celery_beat`, daily | `default` | 2 retries, 60s backoff | Yes — checking for due `MaintenanceCalendarEvent` rows and notifying is safely re-runnable |

### Naming convention
`<verb>_<object>` (e.g. `generate_material_prediction`, not
`material_prediction_task` or `MaterialPredictionTask`) — task names are
also the Celery task registration name and appear in monitoring, so they
must be self-describing without needing the source file open.

## Business Rules
See `ai-engine.md`, `reporting.md`, `business-domain.md` for what each
task's *result* means; this document governs only how the task itself
runs.

## Technical Notes
`config/celery.py` provides the
`Celery("sflms")` app instance and `autodiscover_tasks()` — every future
`apps/<name>/tasks.py` is picked up automatically once that app is in
`INSTALLED_APPS`; no manual task registration required.

## Current Implementation
`config/celery.py` is wired and Docker Compose starts Worker and Beat. The
side-effect-free infrastructure health task, asynchronous report generation,
and the three durable notification jobs listed above are implemented.

Celery processes durable notification/reminder work and FCM/mobile delivery
for eligible CameraEvent-originated SecurityAlerts. It does not publish the live security WebSocket
stream. Committed CameraEvent/SecurityAlert live messages go directly through
Channels and Redis to `/ws/security/events/`, independently of Notification
persistence.

## Future Evolution
- Whether `capture_camera_frame` is itself a recurring Celery Beat task
  per camera, or a single long-running task per camera using an internal
  loop, is not yet decided — needs to be resolved before Phase 6
  implementation starts (affects `celery_worker` concurrency model, see
  `performance.md`).
- Queue routing configuration (`CELERY_TASK_ROUTES`) needs to be added to
  `config/settings/base.py` when the first task ships — not present yet
  since there's nothing to route.

## Important Decisions
Two-queue separation (`default` vs `ai_processing`) decided in advance so
AI load isolation isn't a retrofit — extension of ADR-0008/ADR-0009's
reasoning, not yet its own ADR.

## Developer Notes
Before adding a new task, add its row to the registry table above in the
same PR — a task without a documented retry policy and idempotency
statement does not ship.

## Related Components
`ai-engine.md`, `reporting.md`, `notifications.md`, `performance.md`,
`monitoring-observability.md`.

## Files Involved
`config/celery.py` and implemented or future `apps/<name>/tasks.py` modules.

## Dependencies
`system-architecture.md`, `coding-patterns.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
Any task's retry policy or idempotency guarantee — changing either
without updating this document risks silent duplicate side effects
(e.g., duplicate notifications) going unnoticed.

## Future Improvements
Flower (or equivalent) dashboard for live task/queue monitoring — see
`monitoring-observability.md` §Future Evolution.
