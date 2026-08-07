# 0009. Celery + Redis for Async Processing

## Status
Accepted

## Context
Beyond AI inference (ADR-0008), several other operations are
unsuitable for a synchronous request/response cycle: report generation
(PDF/Excel), material/asset-health predictions, and notification
dispatch. A single, consistent mechanism was needed for all of them
rather than a bespoke solution per feature.

## Decision
Celery (task queue) with Redis (broker + result backend) handles every
operation unsuitable for the request/response cycle, across every domain
app — not just AI. `config/celery.py` provides one shared Celery app
instance (`autodiscover_tasks()`), and `celery-tasks.md` is the
authoritative cross-app task registry.

## Consequences
- One mental model and one piece of infrastructure for all
  background/async work, rather than ad-hoc threading or per-feature
  queuing mechanisms.
- Redis serves three roles (Celery broker, Celery result backend, and
  — from Phase 7 — the Channels layer backend, ADR-0010) on a single
  instance initially, for infrastructure simplicity — documented as a
  known scaling consideration in `system-architecture.md` and
  `performance.md`, with a clear, no-code-change split path
  (`REDIS_URL`'s numbered database suffix) if load ever requires it.
- Requires every task to be designed with an explicit retry policy and
  idempotency statement (`celery-tasks.md`) — a discipline requirement,
  not automatic.

## Alternatives Considered
- **Django-Q or RQ** (simpler task queue alternatives): rejected — Celery
  is more mature for the workload mix here (periodic tasks via Celery
  Beat, retry/backoff policies, and eventual queue-routing needs for AI
  isolation, `celery-tasks.md` §Queue strategy).
- **Threading/async views for "quick" background work**: rejected as an
  inconsistent, harder-to-monitor alternative to a single queuing
  mechanism.

## Related
`celery-tasks.md`. `system-architecture.md`. ADR-0008.
