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
- Versioned base path: `/api/v1/`.
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
| POST | `/api/v1/auth/login/` | none | `AllowAny` | email+password → access+refresh+user |
| POST | `/api/v1/auth/refresh/` | none | `AllowAny` | refresh → new access (rotated) |
| POST | `/api/v1/auth/logout/` | required | `IsAuthenticated` | blacklists refresh token |
| GET | `/api/v1/users/roles/` | required | `IsAuthenticated` | list 4 fixed roles |
| GET/POST | `/api/v1/users/` | required | `IsSuperAdminForWrite` | list/create users |
| GET/PUT/PATCH/DELETE | `/api/v1/users/{id}/` | required | `IsSuperAdminForWrite` | manage one user |
| GET/PATCH | `/api/v1/users/me/` | required | `IsAuthenticated` | own profile |
| POST | `/api/v1/users/change_password/` | required | `IsAuthenticated` | self-service password change |
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

### Phase 4.2 Super Admin project API

Every route below requires the authenticated `super_admin` role. Project
status, actual completion, and Facility conversion are lifecycle outputs and
cannot be written through ordinary create/update payloads.

| Method | Path | Purpose | Success |
|---|---|---|---|
| GET/POST | `/api/v1/projects/` | List or create active Projects | 200/201 |
| GET/PUT/PATCH | `/api/v1/projects/{id}/` | Retrieve or update Project metadata | 200 |
| GET | `/api/v1/projects/overview/` | Project counts and average calculated progress | 200 |
| GET | `/api/v1/projects/monitoring/` | Filterable/paginated Project monitoring | 200 |
| POST | `/api/v1/projects/{id}/start/` | Planning → In Progress service action | 200 |
| POST | `/api/v1/projects/{id}/complete/` | In Progress → Completed; body: `actual_completion_date` | 200 |
| POST | `/api/v1/projects/{id}/convert-to-facility/` | Completed → Operational conversion | 201 |
| GET/POST | `/api/v1/projects/{id}/assignments/` | List, create, or reactivate assignments | 200/201 |
| DELETE | `/api/v1/projects/{id}/assignments/{assignment_id}/` | Soft-remove an assignment | 204 |

Project deletion is not exposed yet: the frozen contract requires dependent
records to be archived through a domain transaction, and no approved archival
service currently exists. Existing `/api/v1/users/` routes remain the Super
Admin user-administration API and are not duplicated here.

### Phase 4.3 Construction Manager phase API

These nested routes require either an active Construction Manager assignment
to the Project or the global Super Admin bypass. An unassigned or cross-project
resource is returned as not found. Ordinary phase writes accept metadata only;
progress and review state are changed exclusively through the Phase 3 services.

| Method | Path | Purpose | Success |
|---|---|---|---|
| GET/POST | `/api/v1/projects/{project_id}/phases/` | List or create Project phases | 200/201 |
| GET/PUT/PATCH | `/api/v1/projects/{project_id}/phases/{id}/` | Retrieve or update phase metadata | 200 |
| GET | `/api/v1/projects/{project_id}/phases/monitoring/` | Phase counts and calculated Project progress | 200 |
| POST | `/api/v1/projects/{project_id}/phases/{id}/progress/` | Record progress through the domain service | 201 |
| GET | `/api/v1/projects/{project_id}/phases/{id}/progress-history/` | Retrieve immutable progress history | 200 |
| GET | `/api/v1/projects/{project_id}/phases/{id}/review-history/` | Retrieve immutable review history | 200 |
| POST | `/api/v1/projects/{project_id}/phases/{id}/approve/` | Approve a phase at 100% | 201 |
| POST | `/api/v1/projects/{project_id}/phases/{id}/reject/` | Finally reject a phase; requires `reason` | 201 |
| POST | `/api/v1/projects/{project_id}/phases/{id}/request-modification/` | Return a phase for modification; requires `reason` | 201 |

Phase deletion is not exposed because final rejected phase archival is reserved
for Super Admin and no approved archival service exists.

### Phase 4.4 Operations Manager API

Operations Managers see only active Facilities linked to them by an active
`FacilityAssignment`; every Asset, MaintenanceOrder, Fault, and Incident
queryset derives its scope from those Facilities. Super Admin retains the
global architecture bypass. Facility lifecycle state and operational Incident
records are read-only in this API.

| Method | Path | Purpose | Success |
|---|---|---|---|
| GET | `/api/v1/facilities/` | List assigned Facilities | 200 |
| GET | `/api/v1/facilities/{id}/` | Retrieve an assigned Facility | 200 |
| GET | `/api/v1/facilities/{id}/monitoring/` | Facility operations summary | 200 |
| GET/POST | `/api/v1/assets/` | List or register Assets in assigned Facilities | 200/201 |
| GET/PUT/PATCH | `/api/v1/assets/{id}/` | Retrieve or update Asset metadata | 200 |
| GET | `/api/v1/assets/monitoring/` | Filterable Asset status and health summary | 200 |
| POST | `/api/v1/assets/{id}/transition-status/` | Transition Asset status through its domain service | 200 |
| GET/POST | `/api/v1/maintenance/orders/` | List or create Maintenance Orders | 200/201 |
| GET/PUT/PATCH | `/api/v1/maintenance/orders/{id}/` | Retrieve or update order metadata | 200 |
| POST | `/api/v1/maintenance/orders/{id}/start/` | Start an open or assigned order | 200 |
| POST | `/api/v1/maintenance/orders/{id}/complete/` | Complete an in-progress order; requires `actual_completion_date` | 200 |
| POST | `/api/v1/maintenance/orders/{id}/close/` | Close a completed order | 200 |
| GET/POST | `/api/v1/faults/` | List or report Faults | 200/201 |
| GET/PUT/PATCH | `/api/v1/faults/{id}/` | Retrieve or update Fault metadata | 200 |
| POST | `/api/v1/faults/{id}/investigate/` | Begin investigation; optional `assigned_engineer` | 200 |
| POST | `/api/v1/faults/{id}/resolve/` | Resolve with `root_cause` and `resolution` | 200 |
| POST | `/api/v1/faults/{id}/close/` | Close a resolved Fault | 200 |
| GET | `/api/v1/operations/incidents/` | Read assigned-Facility Incidents | 200 |
| GET | `/api/v1/operations/incidents/{id}/` | Read one operational Incident | 200 |
| GET | `/api/v1/operations/incidents/{id}/actions/` | Read immutable IncidentAction history | 200 |
| GET | `/api/v1/operations/monitoring/` | Cross-domain assigned-Facility summary | 200 |

Asset status, MaintenanceOrder state, and Fault state are excluded from normal
write payloads and can change only through their service-backed actions. There
are no Facility transition, Incident mutation, deletion, SecurityAlert, camera,
AI, or report-generation routes in this API group.

### Phase 4.5 Security Officer API

Security Officers see only active records belonging to Facilities linked by an
active `FacilityAssignment`; Super Admin retains the global bypass. Incoming
alert fields are read-only, and alert/Incident lifecycle state changes only
through the Phase 3 transactional services.

| Method | Path | Purpose | Success |
|---|---|---|---|
| GET | `/api/v1/security/alerts/` | Filter, search, order, and list scoped alerts | 200 |
| GET | `/api/v1/security/alerts/{id}/` | Retrieve a scoped alert | 200 |
| POST | `/api/v1/security/alerts/{id}/review/` | Review a new alert | 200 |
| POST | `/api/v1/security/alerts/{id}/dismiss/` | Dismiss a reviewed alert with `reason` | 200 |
| POST | `/api/v1/security/alerts/{id}/convert-to-incident/` | Convert a reviewed alert | 201 |
| GET | `/api/v1/security/alerts/{id}/snapshot/` | Authorized protected snapshot download | 200 |
| GET/POST | `/api/v1/security/incidents/` | List or manually create scoped Incidents | 200/201 |
| GET | `/api/v1/security/incidents/{id}/` | Retrieve a scoped Incident | 200 |
| POST | `/api/v1/security/incidents/{id}/start-investigation/` | Start investigation | 200 |
| POST | `/api/v1/security/incidents/{id}/transfer/` | Transfer to an assigned Operations Manager | 200 |
| POST | `/api/v1/security/incidents/{id}/close/` | Close through the domain service | 200 |
| GET/POST | `/api/v1/security/incidents/{id}/actions/` | Read history or append an immutable response action | 200/201 |
| GET/POST | `/api/v1/security/incidents/{id}/evidence/` | List or upload protected Incident evidence | 200/201 |
| GET/POST | `/api/v1/security/incidents/{id}/actions/{action_id}/evidence/` | List or upload protected action evidence | 200/201 |
| GET | `/api/v1/security/evidence/{id}/download/` | Facility-authorized evidence download | 200 |

No raw protected storage path or public file URL is serialized. Incident and
IncidentAction update/delete routes do not exist; response actions are
append-only. Operations Managers retain only their separate read-only Incident
API and cannot call Security Officer mutations.

### Phase 4.6 Reports API

All four active roles may read templates and request reports only for the
modules allowed by the frozen Reports matrix. Super Admin can read every
request and is the only role allowed to create or update templates. Other
users see only report requests they created. Lifecycle and output fields are
service/task-owned and report requests have no update or delete route.

| Method | Path | Purpose | Success |
|---|---|---|---|
| GET/POST | `/api/v1/reports/templates/` | List scoped templates or create one as Super Admin | 200/201 |
| GET/PUT/PATCH | `/api/v1/reports/templates/{id}/` | Retrieve a scoped template or update its supported fields as Super Admin | 200 |
| GET/POST | `/api/v1/reports/requests/` | List visible requests or create and queue a report | 200/202 |
| GET | `/api/v1/reports/requests/{id}/` | Retrieve one visible report request | 200 |
| GET | `/api/v1/reports/requests/{id}/download/` | Download authorized completed PDF/XLSX output | 200 |

Construction Managers may request `construction`, Operations Managers may
request `assets` and `maintenance`, and Security Officers may request
`security`. Super Admin may request every model-supported module, including
`materials`. Request creation calls the existing report service and dispatches
the existing Celery task; generation never runs synchronously in the API.
Queued/processing/failed reports have no downloadable output.

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
See table above — the versioned composition root is `api/v1/urls.py` and
reuses `apps/users/urls.py` and `apps/authentication/urls.py`. The original
unversioned Phase 1 paths remain available for backward compatibility.

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
