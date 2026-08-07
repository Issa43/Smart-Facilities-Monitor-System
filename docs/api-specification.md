# API Specification

## Purpose
The authoritative reference for every REST endpoint: method, URL,
authentication, permissions, request/response shape, and errors. The
live Swagger UI (`/api/docs/`) is generated from code and is always
correct about *current* endpoints; this document additionally captures
*planned* endpoints (not yet in code) and the conventions all of them share.

## Scope
HTTP-layer contract only. Business logic behind each endpoint is
`business-domain.md`; permission *rules* (who) are `permissions-rbac.md`
(this document states which permission class applies, not why).

## Architecture

### Global conventions (every endpoint)
- Base path: `/api/`.
- Auth: `Authorization: Bearer <access_token>` (see `authentication.md`),
  except `login`/`refresh`.
- Pagination envelope (list endpoints):
  ```json
  {
    "count": 42, "total_pages": 3, "current_page": 1, "page_size": 20,
    "next": "...", "previous": null, "results": [ ... ]
  }
  ```
- Error envelope (any 4xx/5xx):
  ```json
  { "success": false, "error": { "code": 403, "message": "...", "details": { ... } } }
  ```
- Filtering/search/ordering: `django-filter` (`?field=value`),
  `SearchFilter` (`?search=...`), `OrderingFilter` (`?ordering=-created_at`)
  — enabled per-ViewSet via `filterset_fields`/`search_fields`.

### Implemented endpoints (Phase 1)

| Method | Path | Auth | Permission | Description |
|---|---|---|---|---|
| POST | `/api/auth/login/` | none | `AllowAny` | email+password → access+refresh+user |
| POST | `/api/auth/refresh/` | none | `AllowAny` | refresh → new access (rotated) |
| POST | `/api/auth/logout/` | required | `IsAuthenticated` | blacklists refresh token |
| GET | `/api/users/roles/` | required | `IsAuthenticated` | list 4 fixed roles |
| GET/POST | `/api/users/` | required | `IsSuperAdminForWrite` | list/create users |
| GET/PUT/PATCH/DELETE | `/api/users/{id}/` | required | `IsSuperAdminForWrite` | manage one user |
| GET/PATCH | `/api/users/me/` | required | `IsAuthenticated` | own profile |
| POST | `/api/users/change_password/` | required | `IsAuthenticated` | self-service password change |
| GET | `/api/schema/`, `/api/docs/`, `/api/redoc/` | none | `AllowAny` | OpenAPI schema + Swagger/Redoc UI |

### Infrastructure endpoints (Phase 2)

These endpoints intentionally live outside `/api/` and do not require
authentication so Docker/orchestrator health probes can call them.

| Method | Path | Dependency | Success | Failure |
|---|---|---|---|---|
| GET | `/health/` | none | 200 process liveness | process unreachable |
| GET | `/health/db/` | PostgreSQL | 200 | 503 |
| GET | `/health/redis/` | Redis cache | 200 | 503 |

Full request/response examples for these are in the live Swagger UI —
not duplicated here to avoid drift; this table is the index, Swagger is
the detail for implemented endpoints.

### Planned endpoint map (Phase 3+, specified not yet implemented)
See `SFLMS_Backend_Architecture_v2.md` §5 at the repository root for the
complete planned endpoint map (Projects, Materials, Facilities, Assets,
Maintenance, Security, AI, Notifications, Reports, Audit). As each group
is implemented, its table is copied into this document (below, per app)
following the exact same table format as above, and from that point this
document is authoritative for it.

<!-- Per-app endpoint tables added here as each app is implemented. -->

## Business Rules
See `business-domain.md` and `permissions-rbac.md`.

## Technical Notes
- Every implemented endpoint's DRF view has `permission_classes` set
  explicitly — never relies solely on the global `DEFAULT_PERMISSION_CLASSES`
  (`IsAuthenticated`) when a stricter rule is needed.
- Custom actions (`@action`) get an auto-generated URL name of
  `<basename>-<method_name_with_dashes>` — e.g. `user-change-password` —
  used directly in tests via `reverse()`, never hardcoded paths.

## Current Implementation
See table above — matches `apps/users/urls.py`, `apps/authentication/urls.py`.

## Future Evolution
Each new domain app's URLs are added to this document's endpoint table in
the same PR that implements them, using the live Swagger output as the
source of truth for exact request/response fields.

## Important Decisions
Consistent pagination/error envelopes across every endpoint, defined once
in `apps.common` (see `backend-architecture.md`), not per-app.

## Developer Notes
When implementing a new endpoint, write its row in this table (or a new
per-app table) as part of the same PR — not as a follow-up.

## Related Components
`authentication.md`, `permissions-rbac.md`, `backend-architecture.md`.

## Files Involved
Every `apps/<domain>/urls.py`, `apps/<domain>/views.py`, `config/urls.py`.

## Dependencies
`glossary.md`, `authentication.md`, `permissions-rbac.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
The global pagination/error envelope shape — the frontend depends on it
verbatim; changing it is a breaking API change requiring versioning
discussion, not a routine update.

## Future Improvements
Once 5+ domain apps exist, consider generating this document's tables
directly from the OpenAPI schema via a small script, rather than
hand-maintaining them.
