# Monitoring & Observability

## Purpose
Defines what "the system is healthy" means operationally, and how a
developer or operator finds out when it isn't — logging strategy, health
checks, and the metrics worth watching.

## Scope
Application-level observability. Infrastructure-level monitoring (host
CPU/disk) is out of scope — a standard Docker host monitoring concern,
not SFLMS-specific.

## Architecture

### Logging strategy
All application logging goes through Python's standard `logging` module
(`config/settings/base.py`'s `LOGGING` dict), never `print()` (see
`coding-standards.md`). Current configuration: console handler only
(`StreamHandler`), `INFO` level by default — Docker captures container
stdout/stderr as the log sink (`docker compose logs backend`,
`docker compose logs celery_worker`), no separate log-shipping
infrastructure yet.

### Health checks (implemented, Phase 2)
```
GET /health/        — liveness: process is up, no dependency access
GET /health/db/     — PostgreSQL readiness (`SELECT 1`)
GET /health/redis/  — Redis cache write/read/delete readiness
```
Dependency failures return 503 with no connection details. Compose uses the
liveness endpoint for the backend container and native health checks for
PostgreSQL/Redis before starting application services.

### What to watch, per service
| Service | Signal worth watching | Why |
|---|---|---|
| `backend` | 5xx rate, response time on `/api/*`, health state | Direct user-facing health |
| `celery_worker` | Queue depth (Redis), task failure rate | Backlog = AI/report/prediction delays going unnoticed |
| `celery_beat` | Missed scheduled runs | Preventive maintenance reminders/predictions silently not firing |
| `postgres` | Connection count, slow query log | Growth-driven degradation (see `performance.md`) |
| `redis` | Memory usage | Shared broker/channel-layer/cache instance — see `system-architecture.md`'s note on splitting if contended |

### Audit trail vs. observability
`AuditLog` (Phase 9, see `security.md`) answers "what did a user do" —
this document's logging/metrics answer "is the system itself functioning
correctly." They are deliberately separate systems serving different
questions; do not conflate application logs with the audit trail, and
never rely on log lines as a substitute for `AuditLog` records or
vice versa.

## Business Rules
N/A.

## Technical Notes
No metrics/APM tool (Prometheus, Sentry, etc.) is integrated yet — see
Future Evolution. Current observability is log-based only, sufficient for
Phase 1–2 scale, explicitly insufficient for production AI-processing
load.

## Current Implementation
Logging configuration exists (`config/settings/base.py` `LOGGING` dict,
console handler) with environment-controlled levels. All three health endpoints
and Compose health checks are implemented.

## Future Evolution
- Structured (JSON) logging for easier aggregation, once a log shipper is
  chosen (not yet decided — candidate: Loki, given Docker-first
  environment fits its typical deployment pattern; not committed).
- Error tracking (Sentry or equivalent) for `celery_worker` exceptions
  especially — YOLO inference failures should not be visible only via
  Docker logs someone happens to be watching.
- Celery task monitoring (Flower or equivalent) once task volume
  justifies a dashboard over `docker compose logs`.

## Important Decisions
Log-to-stdout, Docker-captured, no dedicated log infrastructure yet —
appropriate for current scale, explicitly revisited before production
(see Future Evolution) rather than left as an unstated gap.

## Developer Notes
When adding a new Celery task, always log its start/success/failure at
`INFO`/`ERROR` (see `coding-patterns.md` §Logging) — a task that fails
silently is a debugging nightmare with no APM tool in place yet.

## Related Components
`docker.md`, `celery-tasks.md`, `performance.md`, `security.md` (AuditLog
distinction).

## Files Involved
`config/settings/base.py` (`LOGGING`), `apps/common/health.py`,
`config/urls.py`, `docker-compose.yml`.

## Dependencies
`docker.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
The distinction between AuditLog (business audit trail) and application
logging (operational health) — conflating them is a recurring mistake
worth guarding against explicitly.

## Future Improvements
Health-check endpoints and error tracking are the two highest-priority
additions before any production traffic — see `implementation-phases.md`.
