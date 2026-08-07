# System Architecture

## Purpose
Describes the complete technical system: every service, how they
communicate, and how data flows through the stack. This is the top-level
technical map; `backend-architecture.md` zooms into the Django process
specifically.

## Scope
All runtime components (containers), their responsibilities, and the
protocols between them. Does not cover code-level layering inside Django
(see `backend-architecture.md`) or the database schema itself (see
`database-design.md`).

## Architecture

### Container topology (Docker Compose — official environment, see ADR-0004)

```
                        ┌─────────────────────┐
                        │   Frontend (external,│
                        │   separate repo)      │
                        └──────────┬────────────┘
                                   │ HTTPS / WSS
                                   ▼
                        ┌─────────────────────┐
                        │ backend (Django+DRF)  │──┐
                        │   Gunicorn/Daphne     │  │
                        └───┬─────────────┬─────┘  │
                            │             │         │
                 ┌──────────┘             └───────┐ │
                 ▼                                 ▼ │
        ┌─────────────────┐              ┌──────────────────┐
        │   postgres        │              │   redis            │
        │   (data + audit)  │◄────────────►│   (broker + cache  │
        └─────────────────┘ (via backend) │    + channel layer)│
                                            └────────┬──────────┘
                                                      │
                            ┌─────────────────────────┼─────────────────────┐
                            ▼                          ▼                     ▼
                  ┌──────────────────┐      ┌──────────────────┐  ┌──────────────────┐
                  │  celery_worker     │      │  celery_beat       │  │  channels/asgi     │
                  │  (YOLO inference,  │      │  (scheduled tasks: │  │  (WebSocket layer,  │
                  │  reports, preds)   │      │  preventive maint, │  │ runs in `backend`  │
                  │                    │      │  material checks)  │  │  via Daphne)         │
                  └──────────────────┘      └──────────────────┘  └──────────────────┘
```

All services are declared in a single `docker-compose.yml` at the
repository root (documented in full in `docker.md`). There is no supported
way to run any service outside its container — see ADR-0004.

### Data flow — a representative request
1. Frontend sends `Authorization: Bearer <access_token>` to `backend`.
2. `backend` (DRF) authenticates via JWT, resolves Role + Assignment-based
   queryset filtering, executes business logic (optionally via a Service
   Layer function), reads/writes `postgres`.
3. If the action should trigger async work (e.g., PDF generation), `backend`
   enqueues a Celery task via `redis` (broker) and returns immediately.
4. `celery_worker` picks up the task, does the work, writes results back
   to `postgres` and/or `MEDIA_ROOT` (shared volume).
5. If the event is real-time-worthy (Security Alert, Notification),
   the process publishes to the Channels layer via `redis` (channel
   layer backend), which pushes to any connected WebSocket client.

### AI-specific data flow
```
IP Camera (RTSP) → OpenCV frame capture (inside `celery_worker`)
  → Celery task: YOLO inference
  → CameraDetectionEvent (always written)
  → confidence + deduplication check
  → SecurityAlert (conditionally written)
  → Notification (DB write + Channels broadcast)
```
See `ai-engine.md` for full detail.

## Business Rules
N/A — this document is purely technical; see `business-domain.md`.

## Technical Notes
- **Why Redis serves three roles** (Celery broker, Celery result backend,
  Channels layer): reduces infrastructure footprint for a Docker-first,
  single-VM-capable deployment. If load ever requires it, these can be
  split into separate Redis instances/databases (`REDIS_URL` already uses
  a numbered DB suffix, e.g. `/0`, `/1`, to allow this without code
  changes) — see `performance.md`.
- **Media storage** is a Docker named volume mounted into both `backend` and
  `celery_worker` (both need to read/write uploaded files and AI
  snapshots) — documented fully in `docker.md`.
- **Future cloud migration**: the architecture is deliberately
  container-topology-agnostic beyond Compose — `backend`, `celery_worker`,
  `celery_beat` map directly to separate deployable units (e.g., ECS
  services, Kubernetes deployments) without code changes, and
  `MEDIA_ROOT`'s storage backend is already abstracted (see
  `backend-architecture.md` §Storage) for a future swap to S3-compatible
  object storage.

## Current Implementation
Phase 1 implements the authentication foundation. Phase 2 implements the
Docker topology, Redis cache, Celery/Beat processes, Channels/ASGI foundation,
and health/readiness checks. Domain workers and WebSocket consumers remain
deferred to their owning phases.

## Future Evolution
Phase 6 adds AI tasks/queues and Phase 7 adds authenticated WebSocket consumers
on top of the running Worker/Beat and Channels foundations.

## Important Decisions
Docker-first (ADR-0004), Redis reused for three roles rather than three
separate services (documented above, not yet a standalone ADR — candidate
if reconsidered under load, see `performance.md`).

## Developer Notes
When adding a new container, ask first: does it need `postgres`? Does it
need `redis`? Does it need the media volume? Answer determines its
`docker-compose.yml` service definition — see `docker.md`.

## Related Components
`backend-architecture.md`, `docker.md`, `ai-engine.md`,
`notifications.md`, `performance.md`.

## Files Involved
`docker-compose.yml`, `config/settings/base.py`,
`config/celery.py`, `config/asgi.py`.

## Dependencies
`glossary.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
The Redis-serves-three-roles decision — if split into separate instances,
this diagram and `docker.md` must be updated together.

## Future Improvements
Add a sequence diagram per major workflow (Alert creation, Report
generation) once those flows are implemented and can be verified against
real behavior rather than specified behavior.
