# Backend Architecture

## Purpose
Describes how the Django process itself is organized internally: the
layering model, how apps relate to each other, and the conventions that
keep 13 apps consistent as the codebase grows over years.

## Scope
Code-level architecture inside the `backend`/`celery_worker` containers.
Container topology is `system-architecture.md`; naming/style rules are
`coding-standards.md`; concrete patterns with code shape are
`coding-patterns.md`.

## Architecture

### Layering model (every domain app follows this)
```
HTTP Request
    │
    ▼
urls.py          — routes only, no logic
    │
    ▼
views.py         — ViewSet: permission check, pagination, calls serializer
    │                and/or services.py; NEVER contains business logic itself
    ▼
permissions.py   — object-level filtering (Assignment-based queryset scoping)
    │
    ▼
serializers.py   — validation + shape; may call services.py for
    │                cross-model validation, never writes business logic
    ▼
services.py      — business logic living outside the request/response
    │                cycle: multi-model operations, state transitions,
    │                anything reusable from a Celery task
    ▼
models.py        — schema + model-level invariants only (clean() methods,
                     simple derived properties) — no orchestration
```

**Rule:** if a piece of logic touches more than one model, or would need
to be called from both a view and a Celery task, it belongs in
`services.py`, not in the view and not duplicated in both places. See
`coding-patterns.md` §Service Layer.

### App structure (per domain app)
```
apps/<name>/
├── models.py
├── serializers.py
├── views.py
├── urls.py
├── permissions.py
├── filters.py       # django-filter FilterSets, once an app has >1 filterable field
├── services.py       # business logic layer
├── tasks.py           # Celery tasks (from Phase 6 onward, ai_engine/reports/maintenance)
├── admin.py
├── apps.py
├── migrations/
└── tests/
    ├── test_models.py
    ├── test_api.py
    └── test_services.py   # once services.py has non-trivial logic
```

### Cross-app dependency rules
- Apps may import other apps' `models.py` (FK relationships require this).
- Apps must **not** import other apps' `views.py` or `serializers.py` —
  cross-app composition happens at the URL/router level
  (`config/urls.py`), not by one app calling into another's view layer.
- `apps.common` may be imported by any app. No domain app may be imported
  by `apps.common` (it stays dependency-free of domain concerns).
- `apps.attachments` and `apps.notifications` are consumed by every domain
  app (generic attachment registry, generic notification dispatch) but
  never the reverse.

### The `apps.common` foundation
Every domain model inherits `apps.common.models.BaseModel` (UUID PK, soft
delete, audit timestamps — see `database-design.md`). Every domain
ViewSet's permission stack builds on `apps.common.permissions` (`HasRole`,
`IsSuperAdmin`) plus its own app-level `permissions.py` for object-level
(Assignment-based) filtering. Every list endpoint uses
`apps.common.pagination.StandardResultsPagination`. Every API error passes
through `apps.common.exceptions.custom_exception_handler` for a consistent
envelope. This is deliberate: a new domain app should almost never need to
reinvent any of these four concerns.

### Storage abstraction
`MEDIA_ROOT`/`FileField`/`ImageField` are used exclusively — no view or
service ever constructs a filesystem path manually. `STORAGES["default"]`
in `config/settings/base.py` is the single place a future swap to
S3-compatible storage happens; no model or serializer changes required.

## Business Rules
N/A — technical document; see `business-domain.md`.

## Technical Notes
- Views are DRF `ModelViewSet`/`ReadOnlyModelViewSet` almost universally;
  plain `APIView` is reserved for genuinely non-CRUD endpoints (e.g.
  `LoginView`) — see `coding-patterns.md`.
- `get_queryset()` is where object-level (Assignment-based) filtering
  lives, not `has_object_permission()` — the latter is a defense-in-depth
  backstop against ID-guessing, not the primary filtering mechanism (a
  Construction Manager should never even see a project they're not
  assigned to in a list response).

## Current Implementation
The foundation, authentication, attachment, project, construction, materials,
facility, asset, maintenance, security, and reporting apps implement this
layering. AI, notifications, and audit remain deferred placeholders.

## Future Evolution
Each domain app, on implementation, must match this exact layout. Any
deviation (e.g., an app that skips `services.py` and puts logic directly
in `views.py`) is a defect to fix before merge, not a stylistic choice.

## Important Decisions
UUID PKs (ADR-0011), soft delete (ADR-0012), Service Layer as mandatory
for cross-model logic (see `coding-patterns.md`).

## Developer Notes
Before writing a new endpoint, check whether `apps.common` already solves
your problem (pagination, exceptions, base permissions) before writing
app-specific plumbing.

## Related Components
`folder-structure.md`, `coding-patterns.md`, `coding-standards.md`,
`database-design.md`.

## Files Involved
`apps/common/*`, every `apps/<domain>/*` directory.

## Dependencies
`system-architecture.md`, `glossary.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
The cross-app dependency rule (no app imports another app's views/serializers)
— violating it silently creates coupling that's expensive to unwind later.

## Future Improvements
Once 3+ domain apps exist, consider extracting a shared `filters.py` base
for the extremely common "filter by facility/project + date range" pattern.
