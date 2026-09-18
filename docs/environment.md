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

### Firebase Cloud Messaging

| Variable | Required | Default | Purpose |
|---|---:|---|---|
| `FCM_ENABLED` | No | `False` | Explicitly enables real FCM transport |
| `FCM_PROJECT_ID` | When enabled | unset | Firebase project used by the Admin SDK |
| `FCM_CREDENTIALS_PATH` | When enabled | unset | In-container path to a mounted service-account JSON secret |

The credential file must be mounted at deployment time and must never be
committed, copied into the image, printed, or placed in `.env`. Django and
Celery start normally when FCM is disabled or unconfigured; affected delivery
rows are then recorded as `failed/fcm_unavailable`, never `sent`.

### External safety alerts

| Variable | Required | Default | Purpose |
|---|---:|---|---|
| `SAFETY_ALERTS_ENABLED` | No | `False` | Deployment kill switch for creating project safety alerts from external hazard events |
| `SAFETY_USGS_ENABLED` | No | `True` | Allows USGS earthquake polling (still requires both alerting switches); while on, GDACS earthquakes are not ingested |
| `SAFETY_USGS_FEED_URL` | No | USGS `2.5_day.geojson` summary feed | Must be https on `earthquake.usgs.gov`; any other host is refused |
| `SAFETY_USGS_POLL_SECONDS` | No | `300` | Beat interval, clamped to 60–3600 |
| `SAFETY_GDACS_ENABLED` | No | `True` | Allows GDACS event polling (still requires both alerting switches) |
| `SAFETY_GDACS_EVENTS_URL` | No | GDACS `EVENTS4APP` event list | Must be https on `www.gdacs.org`/`gdacs.org`; any other host is refused |
| `SAFETY_GDACS_POLL_SECONDS` | No | `900` | Beat interval, clamped to 60–3600 |
| `SAFETY_PROVIDER_TIMEOUT_SECONDS` | No | `10` | Per-request timeout, clamped to 1–30 |
| `SAFETY_PROVIDER_MAX_BYTES` | No | `5242880` | Maximum response size, clamped to 64 KiB–20 MiB |
| `SAFETY_PROVIDER_MAX_RETRIES` | No | `2` | Retries for transient provider unavailability, clamped to 0–3 |
| `SAFETY_TELEGRAM_ENABLED` | No | `False` | Kill switch for outbound Telegram delivery of recorded safety decisions. While off, nothing is queued, no delivery row is written, and no request is made |
| `SAFETY_TELEGRAM_BOT_TOKEN` | No | empty | Bot token, read from the environment only. Never commit a real value, and never place it in a fixture, log, audit entry, or API response. Empty while enabled records a `telegram_not_configured` skip instead of sending |
| `SAFETY_TELEGRAM_TIMEOUT_SECONDS` | No | `10` | Per-request timeout, clamped to 1–30 |
| `SAFETY_TELEGRAM_MAX_RETRIES` | No | `3` | Retries for `429`, `5xx`, timeout, and connection failures, clamped to 0–5. Invalid token, invalid chat, and other `4xx` are never retried |
| `SAFETY_TELEGRAM_MAX_MESSAGE_CHARS` | No | `3500` | Outbound message ceiling, clamped to 500–4096 |

The Telegram API base URL is fixed in code at `https://api.telegram.org` and is
deliberately not configurable, so a token cannot be directed at another host.

Alert creation also requires the Super Admin `safety.externalAlerts` system
setting, which is seeded as `false`. While either switch is off, hazard
ingestion writes nothing and provider polls exit before any network call.
Neither provider requires credentials. See `apps/safety/README.md`.

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
| `LOG_FORMAT` | `json` | Structured JSON logs; any other value selects readable text |
| `BACKEND_PORT` | `8000` | Development backend host port |
| `POSTGRES_PORT_FORWARD` | `5432` | Development PostgreSQL host port |
| `REDIS_PORT_FORWARD` | `6379` | Development Redis host port |

### Production hardening

| Variable | Default | Purpose |
|---|---|---|
| `SECURE_SSL_REDIRECT` | `True` in production | Redirect HTTP to HTTPS after TLS proxy exists |
| `SECURE_HSTS_SECONDS` | `31536000` in production | HSTS duration; set to zero only before HTTPS validation |
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
Deployment additionally requires `IMAGE_TAG`; optional image/context variables
are `BACKEND_IMAGE`, `FRONTEND_IMAGE`, `FRONTEND_CONTEXT`, and `APP_HTTP_PORT`.
E2E and backup credentials are runtime-only (`E2E_TEST_PASSWORD`,
`BACKUP_ENCRYPTION_PASSPHRASE`) and must never be committed. AI model variables
remain deferred to the dedicated AI/CV specialist.

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
`python-decouple`, `dj-database-url`, `firebase-admin`.

## Things That MUST NEVER Be Changed Without Updating Documentation
Every new environment variable must be added here and to `.env.example` in the
same change.

## Future Improvements
Use an external secret manager when a concrete production platform is chosen.
