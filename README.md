# SFLMS Backend — Smart Facility Lifecycle Management System

Django/DRF backend for SFLMS. This is a backend-only, REST-only repository;
the frontend is a separate project.

Current implementation:
- Phase 1 foundation: custom User, four fixed Roles, JWT, RBAC scaffolding,
  Swagger/OpenAPI, common model/API utilities.
- Phase 2 infrastructure: Docker Compose, PostgreSQL, Redis, Celery Worker/Beat,
  Redis cache, Channels/ASGI foundation, health checks, persistent volumes.
- Domain apps remain placeholders. No Phase 3 business logic is implemented.

## Official setup

Docker Compose is the only supported runtime.

```bash
cp .env.example .env
# Replace SECRET_KEY and DB_PASSWORD in .env.
docker compose up -d --build
docker compose ps
docker compose exec backend python manage.py check
docker compose exec backend pytest -v
docker compose exec backend python manage.py createsuperuser
```

The development backend is available at `http://localhost:8000`.

| Resource | URL |
|---|---|
| Swagger UI | `http://localhost:8000/api/docs/` |
| ReDoc | `http://localhost:8000/api/redoc/` |
| Django admin | `http://localhost:8000/admin/` |
| Liveness | `http://localhost:8000/health/` |
| PostgreSQL readiness | `http://localhost:8000/health/db/` |
| Redis readiness | `http://localhost:8000/health/redis/` |

## Common commands

```bash
docker compose logs -f backend
docker compose exec backend python manage.py makemigrations --check --dry-run
docker compose exec backend pytest -v
docker compose exec celery_worker celery -A config inspect ping
docker compose down
```

Never use `docker compose down -v` unless permanent deletion of database,
media, Redis, and Beat volumes is explicitly intended.

## Documentation

Start with [docs/README.md](docs/README.md), then read
[docs/onboarding.md](docs/onboarding.md), [docs/docker.md](docs/docker.md),
and [docs/environment.md](docs/environment.md).

The approved architecture remains
[SFLMS_Backend_Architecture_v2.md](SFLMS_Backend_Architecture_v2.md).
