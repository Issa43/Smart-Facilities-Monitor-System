# Docker

## Purpose
Defines the official development and deployment runtime for SFLMS. Docker
Compose is the only supported execution path (ADR-0004).

## Scope
Container build, services, networking, volumes, readiness, startup, and the
difference between development and production Compose workflows. Domain
behavior is outside this document.

## Architecture

### Shared application image
`Dockerfile` builds one Python 3.11 image used by `backend`, `celery_worker`,
and `celery_beat`. It installs pinned dependencies, copies the repository,
creates writable static/media/Celery directories, and runs as the unprivileged
`sflms` user. Each service supplies a different command to the same image.

### Services

| Service | Responsibility | Host exposure |
|---|---|---|
| `backend` | Django ASGI via Daphne; migrations and static collection on startup | Port 8000 in development override only |
| `postgres` | PostgreSQL 16 system of record | Port 5432 in development override only |
| `redis` | Celery broker/result backend, Django cache, Channels layer | Port 6379 in development override only |
| `celery_worker` | Executes infrastructure and future domain tasks | None |
| `celery_beat` | Runs future periodic task schedules | None |
| `frontend` | Versioned Nginx SPA image and `/api/` reverse proxy in production | Port 8080 by default |

PostgreSQL and Redis must pass native health checks before any application
container starts. The shared entrypoint then performs authenticated readiness
checks before launching each process. Only `backend` runs migrations and
`collectstatic`; worker processes never race to do either.

### Compose files
- `docker-compose.yml` is production-oriented: Daphne, production settings,
  no database/Redis host ports, restart policies, named volumes, health gates.
- `docker-compose.override.yml` is applied automatically for local development:
  source bind mounts, development settings, Django `runserver`, and host ports.

Production must explicitly omit the development override and include the
production overlay:

```bash
IMAGE_TAG=<release> docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build
```

### Networking
Every service joins the named `sflms_internal` bridge network. Containers use
service DNS names (`postgres`, `redis`) and never `localhost` for inter-service
connections. PostgreSQL and Redis are not published by the base production
Compose file.

### Persistent volumes
- `postgres_data`: authoritative relational data.
- `redis_data`: Redis AOF state; useful across restarts but not the system of record.
- `static_data`: collected Django/admin static assets.
- `media_data`: uploads and future generated/camera media, shared by backend/worker.
- `celery_beat_data`: persistent Celery Beat schedule file.

Volume deletion (`docker compose down -v`) is destructive and is never part of
the normal stop/restart workflow.

### Startup sequence
1. PostgreSQL and Redis containers start and pass health checks.
2. Application entrypoint runs `docker/wait_for_services.py`.
3. `backend` applies migrations and, in production, collects static files.
4. The requested process starts via `exec`, preserving correct signal handling.
5. Compose monitors backend liveness at `/health/` and worker responsiveness via
   Celery inspect ping.

### Health endpoints
- `GET /health/`: process liveness, no external calls.
- `GET /health/db/`: PostgreSQL `SELECT 1` readiness.
- `GET /health/redis/`: Redis cache write/read/delete readiness.

Dependency checks return HTTP 503 without exposing connection details.

### Static and media
WhiteNoise serves collected Django/admin static files. The frontend image serves
the compiled SPA. Protected media is never mounted into Nginx and is available
only through authenticated Django download actions.

## Business Rules
None. This phase adds infrastructure only and no domain models or APIs.

## Technical Notes
- Redis logical DB 0: Celery; DB 1: Django cache; DB 2: Channels.
- `DATABASE_URL`, when non-empty, overrides component `DB_*` variables.
- The production settings module rejects the known placeholder `SECRET_KEY`.
- Redis AOF is enabled for improved restart durability.
- The ASGI WebSocket router exposes `/ws/security/events/` through JWT
  subprotocol middleware and the existing `ProtocolTypeRouter`. Daphne remains
  the sole application server and Redis database `/2` remains the Channels
  layer; no additional broker or WebSocket service is introduced.

## Current Implementation
Backend/frontend Dockerfiles, development/E2E/restore/production overlays,
entrypoint, readiness scripts, health checks, cache, Celery, and Channels are
implemented and verified locally.

## Future Evolution
- A reverse proxy/TLS service may be added for a concrete deployment target.
- Dedicated AI queues/workers arrive with the AI phase.
- Redis roles may be split into separate instances if measured contention warrants it.

## Important Decisions
Docker-only execution remains ADR-0004. One application image is shared across
backend/worker/beat. The base Compose file is production-oriented and the
override is development-only.

## Developer Notes
Initial development setup:

```bash
cp .env.example .env
# Replace SECRET_KEY and DB_PASSWORD.
docker compose up -d --build
docker compose ps
docker compose exec backend pytest -v
```

Useful commands:

```bash
docker compose logs -f backend
docker compose logs -f celery_worker
docker compose exec backend python manage.py check
docker compose exec backend python manage.py makemigrations --check --dry-run
docker compose down
```

## Related Components
`environment.md`, `deployment.md`, `onboarding.md`,
`monitoring-observability.md`, ADR-0004, ADR-0009, ADR-0010.

## Files Involved
`Dockerfile`, `.dockerignore`, `docker-compose.yml`,
`docker-compose.override.yml`, `docker/*`, `config/settings/*`,
`config/asgi.py`, `config/celery.py`, `apps/common/health.py`.

## Dependencies
Docker Engine with Compose v2.

## Things That MUST NEVER Be Changed Without Updating Documentation
Service names, volume names, Redis logical DB allocation, health endpoint paths,
and the rule that only the backend container runs migrations.

## Future Improvements
Add deployment-specific reverse-proxy/TLS configuration once the production
host/platform is selected.
