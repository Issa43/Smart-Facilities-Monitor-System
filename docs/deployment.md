# Deployment

## Purpose
Defines development and production deployment workflows for the Docker-first
SFLMS backend.

## Scope
Release/runtime procedure. Compose details are in `docker.md`; variables are in
`environment.md`.

## Architecture

### Development
Docker Compose automatically merges `docker-compose.override.yml`:

```bash
cp .env.example .env
# Set a unique SECRET_KEY and DB_PASSWORD.
docker compose up -d --build
docker compose ps
docker compose exec backend pytest -v
```

The override bind-mounts source code, uses development settings and `runserver`,
and publishes backend/PostgreSQL/Redis ports for local tools.

### Production-oriented Compose
Production explicitly excludes the development override:

```bash
docker compose -f docker-compose.yml config
docker compose -f docker-compose.yml build
docker compose -f docker-compose.yml up -d
docker compose -f docker-compose.yml ps
```

The base file uses Daphne with `config.settings.production`, does not publish
PostgreSQL or Redis, applies restart policies, and expects an external reverse
proxy/load balancer to reach backend port 8000 on the Docker network.

### Pre-deployment validation

```bash
docker compose run --rm backend python manage.py check
docker compose run --rm backend python manage.py makemigrations --check --dry-run
docker compose run --rm backend pytest -v
docker compose -f docker-compose.yml config --quiet
```

All commands must pass before deployment. A failing dependency health check or
application check blocks release.

### Startup and migrations
Only the `backend` container has `RUN_MIGRATIONS=1`. The entrypoint waits for
PostgreSQL and Redis, applies existing migrations, collects static files in
production, then starts Daphne. Worker and Beat containers wait for dependencies
but never alter the schema.

### Health verification

```bash
curl http://localhost:8000/health/
curl http://localhost:8000/health/db/
curl http://localhost:8000/health/redis/
docker compose exec celery_worker celery -A config inspect ping
```

The curl examples assume development port publishing or an installed production
reverse proxy.

### Rollback and data safety
Application containers are disposable; named volumes are not. Normal rollback
rebuilds/restarts an earlier application image against retained volumes. Never
run `docker compose down -v` during deployment. Database migration rollback must
follow migration-specific review and is not automated by the entrypoint.

## Business Rules
None.

## Technical Notes
The image is identical across backend/worker/beat and across environments.
Environment variables and commands supply all runtime differences.

## Current Implementation
Local and production-oriented Compose workflows are implemented. A concrete
reverse proxy/TLS configuration and CI/CD automation are not yet selected.

## Future Evolution
- Add reverse proxy and TLS configuration for the selected host/platform.
- Add automated image publishing and deployment after repository hosting is fixed.
- Add zero-downtime rollout mechanics if traffic scale requires them.

## Important Decisions
The production command must explicitly omit the override file. Database and
Redis ports are never exposed by the base Compose definition.

## Developer Notes
Inspect `docker compose config` before every deployment; it is the authoritative
merged configuration and catches missing required variables early.

## Related Components
`docker.md`, `environment.md`, `monitoring-observability.md`,
`backup-recovery.md`.

## Files Involved
`Dockerfile`, Docker Compose files, `.env`, `docker/*`, production settings.

## Dependencies
Docker Engine/Compose v2 and a production reverse proxy for external traffic.

## Things That MUST NEVER Be Changed Without Updating Documentation
Single-image deployment, backend-only migration ownership, and the rule that
production excludes the development override.

## Future Improvements
Add CI/CD and a deployment-specific TLS proxy once the production platform is
chosen.
