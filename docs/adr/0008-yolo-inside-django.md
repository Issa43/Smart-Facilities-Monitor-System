# 0008. YOLO Inference Inside Django (via Celery)

## Status
Accepted

## Context
SFLMS requires computer-vision-based security detection (fire, smoke,
intrusion, unauthorized presence, later license plate recognition) from
IP camera streams. The explicit requirement was no microservices at this
stage — YOLO must run inside the same Django backend, not as a separate
service.

## Decision
YOLO/OpenCV processing runs inside the same codebase and deployment unit
as the rest of the backend, but never inline in a request/response cycle
— all frame capture and inference happens in `celery_worker` (a
container running the same image, different process), fully decoupled
from `web`'s request handling via Celery + Redis (see ADR-0009).

## Consequences
- No additional service to deploy/operate at this stage — lower
  operational complexity, consistent with the "no microservices yet"
  requirement.
- `web` (the API process) is never blocked by inference work, regardless
  of camera count or model latency.
- The `ai_engine` app's task boundary (`apps/ai_engine/tasks.py`) is a
  deliberate, natural extraction point if a future service split is ever
  needed (GPU resource isolation, independent scaling) — this design
  doesn't build that split now, but doesn't preclude it either.
- `celery_worker`'s resource requirements (CPU/GPU for inference) are
  coupled to the same image as `web`/`celery_beat`, meaning the shared
  `Dockerfile` (see `docker.md`) must accommodate whatever YOLO's runtime
  dependencies require, even though `web` itself doesn't need them —
  accepted tradeoff for a single-image simplicity, revisit if image size
  or dependency conflicts become a real problem.

## Alternatives Considered
- **Separate AI microservice** (its own deployable, its own API,
  called by Django): explicitly rejected — contrary to the "no
  microservices at this stage" requirement. Remains the natural future
  direction if warranted (see `future-roadmap.md`).
- **Synchronous inference inside a Django view**: rejected outright —
  would block the API on every inference call, unacceptable regardless
  of the microservice question.

## Related
`ai-engine.md`. `camera-processing.md`. `system-architecture.md`.
ADR-0009.
