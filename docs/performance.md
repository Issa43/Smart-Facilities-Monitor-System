# Performance

## Purpose
The performance posture and budget for the system — what's expected to
scale by default, what's a known future bottleneck, and how to reason
about the latter when it becomes real.

## Scope
Backend and infrastructure performance. Frontend rendering performance is
out of scope (separate repository).

## Architecture

### Default-scalable by design
- UUID PKs + `select_related`/`prefetch_related` used deliberately on
  every FK-heavy queryset (e.g., `ProjectViewSet.get_queryset()` pattern
  in `coding-patterns.md`) — N+1 queries are treated as a defect, not a
  later optimization.
- Pagination (`StandardResultsPagination`, page_size=20, max 100) is
  global and mandatory — no endpoint returns an unbounded list.
- Indexes are added per documented query pattern (see `database-design.md`)
  — not speculatively, but also not deferred until a slow-query report forces
  it retroactively for obvious cases (e.g., `User.email` lookup on every
  login).

### Known future bottlenecks (identified in advance, not yet hit)
| Area | Risk | Mitigation strategy (when needed) |
|---|---|---|
| Camera frame capture | `celery_worker` CPU/GPU load scales linearly with active camera count | Dedicated worker pool/queue for `ai_engine` tasks, separate from general-purpose Celery tasks (see `celery-tasks.md`); GPU-backed worker container if YOLO throughput requires it |
| Redis (3 roles) | Celery broker + Channels layer + cache all on one instance could contend under load | Split into separate Redis logical DBs (`REDIS_URL` already numbered, e.g. `/0` vs `/1`) or separate instances — no code change required, only `docker-compose.yml`/env changes |
| PostgreSQL writes from `CameraDetectionEvent` | Every qualifying frame writes a row — high-volume table by design (ai-engine.md) | Partitioning by `created_at` (monthly) once volume is measured; not implemented speculatively |
| Report generation | Large Excel/PDF exports could be slow/memory-heavy in a single Celery task | Chunked/streamed generation if a real report size proves problematic — not designed for hypothetically-large data upfront |

### Query budget
No documented hard SLA yet (no production traffic exists) — this section
will be replaced with real numbers once Phase 10 (integration testing)
produces baseline measurements. Until then: the qualitative rule is "no
endpoint executes an unbounded or O(n²) query pattern," enforced by code
review, not automated yet.

## Business Rules
N/A.

## Technical Notes
`django-extensions` (in `requirements.txt`, dev-only) provides
`graph_models` and other introspection tools useful for spotting
relationship-driven query risk before it ships.

## Current Implementation
Phase 1's only queries (`User`/`Role` list/detail) are trivially small —
no performance work needed yet beyond the defaults above.

## Future Evolution
This document gains real numbers (query counts, response time
percentiles) once Phase 10 integration testing runs against realistic
data volumes — currently all entries above are risk *anticipation*, not
measurement.

## Important Decisions
Pagination is non-optional and global — no endpoint is exempted, even
"small" reference-data endpoints like `/api/users/roles/`.

## Developer Notes
Before adding a new list endpoint, ask: what's the realistic max row
count in production for this table, and does the queryset use
`select_related`/`prefetch_related` for every FK it touches in the
serializer?

## Related Components
`database-design.md`, `celery-tasks.md`, `system-architecture.md`.

## Files Involved
`apps/common/pagination.py` and every domain `views.py`.

## Dependencies
`database-design.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
The mandatory-pagination rule.

## Future Improvements
Add `django-silk` or equivalent query-profiling middleware in the
development Docker Compose override once real domain apps exist to
profile.
