# Monitoring and Observability

## Implemented signals

- JSON logs to stdout by default (`LOG_FORMAT=json`), including timestamp,
  level, logger, message, and exception details. Docker or the hosting platform
  is responsible for shipping and retention.
- `GET /health/` for liveness, `/health/db/` for PostgreSQL readiness, and
  `/health/redis/` for cache/Redis readiness.
- `GET /metrics/` in Prometheus text format, exposing process uptime, labelled
  HTTP request counts and cumulative latency, database availability, and Celery
  queue depth.
- `python manage.py monitor_health --max-queue-depth 100` exits non-zero when
  PostgreSQL, Redis, or queue thresholds fail. Run it from a scheduler whose
  non-zero exit/webhook policy provides the alert destination.
- Celery tasks log terminal failures; report failures persist their reason and
  expose retry. Backup/restore scripts also fail closed with non-zero exits.

The backend and infrastructure services remain internal in production; expose
metrics only to the selected monitoring network. AuditLog is the business audit
trail and must not be replaced by operational logs.

## Operator checks

```powershell
docker compose exec backend python manage.py monitor_health
docker compose exec celery_worker celery -A config inspect ping
curl http://backend:8000/metrics/
```

The concrete log collector, metrics scraper, alert receiver, and error-tracking
vendor depend on the hosting platform and are external deployment decisions.
Structured logs and non-zero health hooks are ready for those integrations; no
vendor credentials are embedded.
