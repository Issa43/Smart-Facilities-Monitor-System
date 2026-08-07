# AI Engine

## Purpose
Explains the computer-vision pipeline end-to-end: how a video frame
becomes a Security Alert, and how material/asset predictions are produced
— the design that lets YOLO run inside Django without blocking API
requests.

## Scope
The AI processing pipeline and its data model. Camera *ingestion*
mechanics (RTSP handling, recording storage) are `camera-processing.md`;
what happens after an Incident is created is `business-domain.md`.

## Architecture

### Detection pipeline (specified, Phase 6)
```
IP Camera (RTSP)
    │
    ▼
OpenCV frame capture  (runs inside celery_worker, NOT inside a web request)
    │  captures at a configured rate, not every frame
    ▼
Celery task: process_frame(camera_id, frame)   — fully async, non-blocking
    │
    ▼
YOLO inference
    │
    ▼
confidence >= per-detection-type threshold?
    │
   ┌┴───────────┐
  NO            YES
   │              │
 discard    CameraDetectionEvent   ← ALWAYS written (AI's own audit trail,
                │                      independent of SecurityAlert)
                ▼
      deduplication check: open SecurityAlert already exists for
      (camera, detection_type) within the dedup window?
                │
        ┌───────┴────────┐
       YES                NO
        │                  │
   attach as another   new SecurityAlert
   detection on the    (source="ai_detection")
   existing alert            │
   (no new alert)            ▼
                        Notification (DB write + Channels broadcast
                                       to assigned Security Officers)
```

### Prediction pipelines (specified, Phase 3/4 + 6)
- **Material consumption prediction**: `MaterialConsumptionRecord` history
  → periodic Celery task → `MaterialPrediction`
  (`predicted_date`, `predicted_quantity`, `confidence_score`). Advisory
  only — never auto-creates a `MaterialRequest` (see `business-domain.md`).
- **Asset health prediction**: maintenance/fault history → periodic Celery
  task → `AssetHealthHistory` row (`health_score`, `risk_level`,
  `remaining_useful_life`, `prediction_source`). Feeds the Asset Health
  Center charts; advisory only, never auto-creates a `MaintenanceOrder`.

### False positive review loop
`SecurityAlert.is_false_positive` / `reviewed_by` / `review_notes` are set
by a Security Officer reviewing a past alert. This is intentionally
**not** a delete or hide operation — false-positive rate per
`detection_type`/camera is itself a metric worth tracking to decide when
to raise or lower a threshold, so the original alert record is preserved.

### Vehicle recognition
`VehicleRecognition` (plate_number, vehicle_type, entry_time, exit_time,
confidence) is a parallel, independent pipeline sharing the same camera
frame-capture layer but a different model (`AIModel.type="vehicle_recognition"`)
— it does not produce `SecurityAlert` rows by default (an unrecognized or
unauthorized plate could, as a future rule — see Future Evolution).

## Business Rules
See `business-domain.md` §AI Lifecycle for the full rule set. Key
constraints repeated here for AI-specific context:
- Every qualifying inference is logged (`CameraDetectionEvent`) whether or
  not it becomes an Alert — this is non-negotiable for auditability of
  the AI system's own behavior, independent of the Security audit trail.
- Deduplication window and per-type confidence thresholds are
  configuration (see `environment.md`), not hardcoded — tunable without a
  code deploy.

## Technical Notes
- **Why YOLO runs inside Django** rather than a separate microservice:
  reduces operational complexity for the current Docker-first, single
  deployment target while keeping inference off the request/response
  cycle via Celery (ADR-0008). The architecture is deliberately not
  precluding a future extraction — `ai_engine`'s `tasks.py` boundary is
  exactly where a future service split would happen, with `celery_worker`
  becoming a remote caller instead of an in-process one.
- **Model versioning**: `AIModel` (`name`, `type`, `version`, `status`)
  lets multiple model versions coexist during a rollout; every
  `CameraDetectionEvent` records which `AIModel` produced it.
- **Frame rate and thresholds**: not yet finalized with real numbers —
  tracked as an open question, see Future Evolution.

## Current Implementation
Not implemented. `apps/ai_engine/` is a placeholder. This document
specifies the Phase 6 target.

## Future Evolution
Open questions to resolve before/during Phase 6 implementation (carried
over from the architecture review, not yet decided):
- Per-`detection_type` confidence thresholds (proposed starting point:
  Fire=0.75, Smoke=0.70, Intrusion=0.60 — needs validation against real
  model performance, not guessed values to ship as-is).
- Deduplication window (proposed starting point: 60 seconds, tunable).
- Frame capture rate per camera (affects `celery_worker` load directly —
  needs a load test once real cameras are available, not a desk decision).
- Whether unauthorized vehicle recognition should raise a `SecurityAlert`
  — currently out of scope, flagged as a candidate for `future-roadmap.md`.

## Important Decisions
YOLO inside Django + Celery (ADR-0008). DetectionEvent kept structurally
separate from SecurityAlert (documented in `business-domain.md`, not yet
its own ADR — candidate if ever revisited).

## Developer Notes
Never call YOLO inference synchronously from a view or serializer — it
must always be a Celery task. If you find yourself importing a YOLO model
in `views.py`, that's a defect.

## Related Components
`camera-processing.md`, `notifications.md`, `business-domain.md`,
`celery-tasks.md`.

## Files Involved
`apps/ai_engine/*` (not yet created), `apps/security/models.py` (future,
`SecurityAlert`, `Incident`).

## Dependencies
`glossary.md`, `business-domain.md`, `celery-tasks.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
The rule that every qualifying detection is logged regardless of alert
conversion. The advisory-only nature of predictions.

## Future Improvements
License plate recognition against an authorized-vehicle allowlist (raises
the vehicle pipeline from passive logging to active alerting) — tracked
in `future-roadmap.md`, not scheduled to a phase yet.
