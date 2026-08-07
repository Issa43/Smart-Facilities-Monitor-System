# Environment

## Purpose
Defines every supported environment variable and its Docker behavior.

## Scope
Configuration only. Service topology is documented in `docker.md`.

## Architecture

### Django

| Variable | Required | Default/example | Purpose |
|---|---:|---|---|
| `DJANGO_SETTINGS_MODULE` | No | `config.settings.development` | Settings module; Compose overrides it per environment |
| `SECRET_KEY` | Production | placeholder | Django/JWT signing secret; placeholder is rejected in production |
| `DEBUG` | No | `True` in example | Debug behavior; production settings always force false |
| `ALLOWED_HOSTS` | Production | `localhost,127.0.0.1,backend` | Allowed Host headers |
| `CSRF_TRUSTED_ORIGINS` | Deployment-specific | `http://localhost:8000` | Trusted origins for session-based Django admin |
| `CORS_ALLOWED_ORIGINS` | Deployment-specific | local frontend origins | Separate frontend origins |

### PostgreSQL

| Variable | Required | Default/example | Purpose |
|---|---:|---|---|
| `DATABASE_URL` | No | unset | Full PostgreSQL URL; overrides all component DB settings |
| `DB_NAME` | Yes in Compose | `sflms_db` | Database name / `POSTGRES_DB` |
| `DB_USER` | Yes in Compose | `sflms_user` | Database user / `POSTGRES_USER` |
| `DB_PASSWORD` | Yes | placeholder | Database password / `POSTGRES_PASSWORD` |
| `DB_HOST` | No | `postgres` | Docker service hostname |
| `DB_PORT` | No | `5432` | Container database port |
| `DB_CONN_MAX_AGE` | No | `60` | Django persistent connection lifetime, seconds |
| `DB_SSL_REQUIRE` | No | `False` | Add SSL requirement when parsing `DATABASE_URL` |

`DATABASE_URL` should normally remain unset in local Compose so changing
`DB_PASSWORD` cannot drift from an independently copied URL. It is supported for
managed production databases that provide a single connection string.

### Redis, cache, Celery, Channels

| Variable | Required | Default | Purpose |
|---|---:|---|---|
| `REDIS_URL` | No | `redis://redis:6379/0` | Shared base/Celery Redis URL |
| `CACHE_URL` | No | `redis://redis:6379/1` | Django default cache |
| `CHANNEL_REDIS_URL` | No | `redis://redis:6379/2` | Channels layer |
| `CACHE_DEFAULT_TIMEOUT` | No | `300` | Cache timeout in seconds |
| `CELERY_BROKER_URL` | No | `REDIS_URL` | Celery broker override |
| `CELERY_RESULT_BACKEND` | No | `REDIS_URL` | Celery results override |

### JWT

| Variable | Required | Default | Purpose |
|---|---:|---|---|
| `ACCESS_TOKEN_LIFETIME_MINUTES` | No | `30` | Access-token lifetime |
| `REFRESH_TOKEN_LIFETIME_DAYS` | No | `7` | Refresh-token lifetime |

### Container startup

| Variable | Default | Purpose |
|---|---|---|
| `WAIT_FOR_SERVICES` | `1` | Run PostgreSQL/Redis readiness checks |
| `SERVICE_WAIT_TIMEOUT` | `60` | Maximum wait in seconds per dependency |
| `SERVICE_WAIT_INTERVAL` | `2` | Retry interval in seconds |
| `RUN_MIGRATIONS` | `0` | Apply migrations before process start; Compose enables only for backend |
| `COLLECT_STATIC` | `0` | Collect static files; production backend enables it |

### Logging and host ports

| Variable | Default | Purpose |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Root application log level |
| `DJANGO_LOG_LEVEL` | `INFO` | Django logger level |
| `BACKEND_PORT` | `8000` | Development backend host port |
| `POSTGRES_PORT_FORWARD` | `5432` | Development PostgreSQL host port |
| `REDIS_PORT_FORWARD` | `6379` | Development Redis host port |

### Production hardening

| Variable | Default | Purpose |
|---|---|---|
| `SECURE_SSL_REDIRECT` | `False` | Redirect HTTP to HTTPS after TLS proxy exists |
| `SECURE_HSTS_SECONDS` | `0` | HSTS duration; enable only after HTTPS validation |
| `USE_X_FORWARDED_PROTO` | `True` | Trust reverse proxy `X-Forwarded-Proto` for HTTPS detection |

## Business Rules
`.env` is never committed. `.env.example` contains placeholders only. Secrets
must be replaced before any shared or production deployment.

## Technical Notes
All application configuration is read through `python-decouple` in settings,
except standard `DJANGO_SETTINGS_MODULE` bootstrapping and container-only
startup flags read by the entrypoint/readiness script.

## Current Implementation
All variables above are represented in `.env.example` or have documented
settings fallbacks. Docker service hostnames are the official defaults.

## Future Evolution
Email, object-storage, AI model, and deployment-platform variables will be
added only when their owning phases implement those capabilities.

## Important Decisions
Redis logical databases are separated by concern while sharing one instance.
`DATABASE_URL` is optional and takes precedence when present.

## Developer Notes
Copy `.env.example` to `.env`, replace `SECRET_KEY` and `DB_PASSWORD`, and do
not quote values unless the quotes are intentionally part of the value.

## Related Components
`docker.md`, `deployment.md`, `security.md`.

## Files Involved
`.env.example`, `config/settings/base.py`, `config/settings/production.py`,
`docker-compose.yml`, `docker-compose.override.yml`, `docker/*`.

## Dependencies
`python-decouple`, `dj-database-url`.

## Things That MUST NEVER Be Changed Without Updating Documentation
Every new environment variable must be added here and to `.env.example` in the
same change.

## Future Improvements
Use an external secret manager when a concrete production platform is chosen.
