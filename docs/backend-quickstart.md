# SFLMS Backend — Smart Facility Lifecycle Management System

Django/DRF backend for SFLMS. This is a backend-only, REST-only repository;
the frontend is a separate project.

Current implementation includes JWT authentication, four-role RBAC and object
scoping, project/construction/material workflows, facilities/assets/maintenance,
security incidents and protected files, asynchronous PDF/XLSX reports,
notifications, audit logs, analytics, Docker/Celery infrastructure, encrypted
backup/restore tooling, metrics, and a separate React frontend. AI/Computer
Vision remains an integration-ready foundation only; models and inference are
deferred to a dedicated specialist.

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
| Prometheus metrics | `http://localhost:8000/metrics/` |

## Common commands

```bash
docker compose logs -f backend
docker compose exec backend python manage.py makemigrations --check --dry-run
docker compose exec backend pytest --ds=config.settings.test --create-db -q
docker compose exec celery_worker celery -A config inspect ping
docker compose exec backend python manage.py monitor_health
docker compose down
```

Never use `docker compose down -v` unless permanent deletion of database,
media, Redis, and Beat volumes is explicitly intended.

## Documentation

Start with [README.md](README.md), then read
[onboarding.md](onboarding.md), [docker.md](docker.md),
and [environment.md](environment.md).

The approved architecture remains
[reports/SFLMS_Backend_Architecture_v2.md](reports/SFLMS_Backend_Architecture_v2.md).
