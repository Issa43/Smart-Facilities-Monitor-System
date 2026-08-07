# Camera Processing

## Purpose
Explains how video reaches the system and how it's stored — the
ingestion and storage layer that `ai-engine.md`'s inference pipeline
consumes.

## Scope
RTSP stream handling, frame capture mechanics, recording storage. Model
inference itself is `ai-engine.md`; how resulting alerts flow to users is
`notifications.md`.

## Architecture

### Camera registration
Each `Camera` (facility, name, location, camera_type, ip_address,
`stream_url`, status, `last_connection`) represents one physical IP
camera. `enabled_detections` (planned field, JSON list) controls which
detection types run against that specific camera — not every camera needs
every model (a camera pointed at a stairwell may not need vehicle
recognition).

### Ingestion (specified, Phase 6)
```
Camera.stream_url (RTSP)
    │
    ▼
OpenCV VideoCapture — runs inside celery_worker as a long-running
    process/task per active camera, not inside the web process
    │
    ▼
Frame sampled at a configured rate (see ai-engine.md §Future Evolution
    for the open question on exact rate)
    │
    ▼
Frame handed to the YOLO inference task (ai-engine.md)
```
**Why `celery_worker`, not `web`:** the `web` process must stay responsive
to API requests; a blocking `VideoCapture.read()` loop has no place in a
request/response cycle. This mirrors the general async-processing
decision (ADR-0008/ADR-0009).

### Recording storage
`CameraRecording` (camera, video_file, start_time, end_time,
`event_related_id`) stores video clips — typically triggered around a
detection event, not continuous 24/7 recording (storage cost).
`event_related_id` deliberately has no hard FK (nullable UUID) so a
recording can reference either a `CameraDetectionEvent` or a
`SecurityAlert` without two mutually-exclusive nullable FK columns.

### Local vs. future cloud storage
Recordings and snapshots use the same `MEDIA_ROOT`/`FileField`
abstraction as every other upload in the system (see
`backend-architecture.md` §Storage abstraction) — no camera-specific
storage code path. This matters more here than anywhere else in the
system because video files are large; the abstraction is what makes a
future move to object storage (S3-compatible) a configuration change, not
a rewrite.

## Business Rules
- A camera with `status="offline"` should not have frame-capture tasks
  scheduled against it — avoids wasted Celery cycles retrying a dead
  stream (exact retry/backoff policy is a Phase 6 implementation detail,
  tracked in `celery-tasks.md` once written).
- Recording retention policy (how long clips are kept) is not yet decided
  — see Future Evolution and `backup-recovery.md`.

## Technical Notes
RTSP handling has no built-in health-check today; `Camera.last_connection`
is the planned field for a heartbeat mechanism, updated by whatever
process maintains the `VideoCapture` connection.

## Current Implementation
Camera and CameraRecording are not in the approved Phase 3 scope. The security
app is implemented for SecurityAlert, Incident, and IncidentAction; camera and
AI integration remain deferred to the later integration phase.

## Future Evolution
- Recording retention/rotation policy — open question, see
  `backup-recovery.md`.
- Camera health-check/reconnection strategy for dropped RTSP streams —
  not yet designed.
- Multi-camera load on a single `celery_worker` — needs a concurrency
  strategy (worker pool sizing) once real camera count is known; see
  `performance.md`.

## Important Decisions
Ingestion happens in `celery_worker`, never in `web` (extension of
ADR-0008's reasoning). Recordings use the same storage abstraction as
every other file in the system (extension of the general storage
decision in `backend-architecture.md`).

## Developer Notes
Do not write camera-stream-handling code inside `apps/ai_engine`'s
inference task itself — frame *capture* and frame *inference* are
separable concerns and should stay in separate Celery tasks so one can be
scaled/tuned independently of the other.

## Related Components
`ai-engine.md`, `notifications.md`, `celery-tasks.md`, `performance.md`.

## Files Involved
`apps/security/models.py` (future, `Camera`, `CameraRecording`),
`apps/ai_engine/tasks.py` (future, frame capture task).

## Dependencies
`glossary.md`, `ai-engine.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
The rule that frame capture never runs inside the `web` process.

## Future Improvements
Camera health dashboard (`last_connection` staleness → operational alert)
— tracked in `future-roadmap.md`.
