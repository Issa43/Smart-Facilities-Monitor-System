# Onboarding

## Purpose
Provides the official zero-to-running development workflow.

## Scope
Docker Compose development setup. Production operation is `deployment.md`.

## Architecture

### Prerequisites
- Docker Engine/Desktop with Compose v2.
- Git for obtaining the repository.
- No host Python, PostgreSQL, or Redis installation.

### First-time setup

```bash
git clone <repository-url>
cd sflms
cp .env.example .env
```

Edit `.env` and replace at minimum:
- `SECRET_KEY` with a long random value.
- `DB_PASSWORD` with a non-placeholder password.
- `CORS_ALLOWED_ORIGINS`/`CSRF_TRUSTED_ORIGINS` for your frontend/admin origins.

Then start and verify:

```bash
docker compose up -d --build
docker compose ps
docker compose exec backend python manage.py check
docker compose exec backend python manage.py createsuperuser
docker compose exec backend pytest -v
```

The backend startup entrypoint applies migrations automatically. Running the
explicit check/test commands is still required before beginning feature work.

### Daily workflow

```bash
docker compose up -d
docker compose logs -f backend
docker compose exec backend pytest -v
docker compose exec backend python manage.py makemigrations --check --dry-run
docker compose down
```

Do not add `-v` to `docker compose down`; it would delete persistent data.

### URLs
- API documentation: `http://localhost:8000/api/docs/`
- Django admin: `http://localhost:8000/admin/`
- Liveness: `http://localhost:8000/health/`
- PostgreSQL readiness: `http://localhost:8000/health/db/`
- Redis readiness: `http://localhost:8000/health/redis/`

### Troubleshooting

```bash
docker compose config
docker compose ps
docker compose logs backend postgres redis celery_worker celery_beat
docker compose exec postgres pg_isready -U "$DB_USER" -d "$DB_NAME"
docker compose exec redis redis-cli ping
docker compose exec celery_worker celery -A config inspect ping
```

If a host port is occupied, change `BACKEND_PORT`,
`POSTGRES_PORT_FORWARD`, or `REDIS_PORT_FORWARD` in `.env`.

## Business Rules
None.

## Technical Notes
The development override is loaded automatically. Production must use only
`docker-compose.yml`; see `deployment.md`.

## Current Implementation
The Docker-only workflow is implemented. Runtime execution still depends on a
host with Docker available.

## Future Evolution
Convenience wrappers (`Makefile`/`justfile`) may be added without replacing the
documented Compose commands.

## Important Decisions
There is no supported host-Python workflow (ADR-0004).

## Developer Notes
Read `docs/README.md`, `glossary.md`, `project-overview.md`,
`business-domain.md`, `system-architecture.md`, and `coding-standards.md`
before implementing domain code.

## Related Components
`docker.md`, `environment.md`, `deployment.md`, `testing.md`.

## Files Involved
Docker files, `.env.example`, and this document.

## Dependencies
Docker Engine/Compose v2.

## Things That MUST NEVER Be Changed Without Updating Documentation
The Docker-only execution rule and first-time setup commands.

## Future Improvements
Add platform-specific Docker Desktop troubleshooting only when a reproducible
platform issue is identified.
