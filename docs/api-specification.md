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

### Construction Manager project-record API

These routes require either an active Construction Manager assignment to the
Project or the global Super Admin bypass. Collection results are limited to
assigned Projects, and cross-project related objects are rejected.

| Method | Path | Purpose | Success |
|---|---|---|---|
| GET/PUT/PATCH | `/api/v1/construction/projects/{id}/` | Read or update assigned Project metadata | 200 |
| GET | `/api/v1/construction/projects/{id}/image/` | Download the assigned Project image | 200 |
| GET | `/api/v1/construction/projects/{id}/completion-check/` | Evaluate completion prerequisites | 200 |
| POST | `/api/v1/construction/projects/{id}/complete/` | Complete an eligible Project | 200 |
| GET | `/api/v1/construction/phases/` | Read assigned Project phases as a flat collection | 200 |
| GET/POST/PUT/PATCH/DELETE | `/api/v1/construction/materials/` | Manage assigned-Project materials | 200/201/204 |
| GET/POST | `/api/v1/construction/materials/{id}/consumption/` | Read or record material consumption | 200/201 |
| GET/POST/PUT/PATCH/DELETE | `/api/v1/construction/material-requests/` | Construction Managers manage requests within assigned Projects; Super Admin has global read access | 200/201/204 |
| POST | `/api/v1/construction/material-requests/{id}/{review,approve,reject}/` | Super Admin reviews, approves, or rejects a request | 200 |
| POST | `/api/v1/construction/material-requests/{id}/complete/` | Apply the existing downstream completion transition to an approved request | 200 |
| GET/POST/PUT/PATCH/DELETE | `/api/v1/construction/daily-reports/` | Manage daily reports | 200/201/204 |
| GET/POST/PUT/PATCH/DELETE | `/api/v1/construction/quality-inspections/` | Manage quality inspections | 200/201/204 |
| GET/POST/DELETE | `/api/v1/construction/documents/` | Manage Project documents | 200/201/204 |
| GET | `/api/v1/construction/documents/{id}/download/` | Authenticated document download | 200 |
| GET/POST/DELETE | `/api/v1/construction/site-photos/` | Manage Project site photos | 200/201/204 |
| GET | `/api/v1/construction/site-photos/{id}/download/` | Authenticated site-photo download | 200 |

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
| GET/PUT/PATCH/DELETE | `/api/v1/assets/{id}/` | Retrieve/update Asset metadata, or safely archive an Asset without operational history | 200/204 |
| GET | `/api/v1/assets/filter-options/` | Return distinct scoped Asset Types, categories, and manufacturers from persisted Assets | 200 |
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
is no separate Asset Type table: `asset_type` is the persisted, required Asset
field. Maintenance responses derive it from the selected Asset, while writes
may submit it only as a consistency check. Filter-option values are distinct
values from the caller's assigned-Facility Asset queryset, not a parallel
vocabulary. There
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
| GET/POST | `/api/v1/security/incidents/{id}/actions/` | Read or append a pending response action | 200/201 |
| PATCH | `/api/v1/security/incidents/{id}/actions/{action_id}/completion/` | Mark a response action complete or pending | 200 |
| GET/POST | `/api/v1/security/incidents/{id}/evidence/` | List or upload protected Incident evidence | 200/201 |
| GET/POST | `/api/v1/security/incidents/{id}/actions/{action_id}/evidence/` | List or upload protected action evidence | 200/201 |
| GET | `/api/v1/security/evidence/{id}/download/` | Facility-authorized evidence download | 200 |

No raw protected storage path or public file URL is serialized. Incident and
IncidentAction content update/delete routes do not exist; response-action text
is append-only, while completion state changes only through the dedicated
completion action. Operations Managers retain only their separate read-only
Incident API and cannot call Security Officer mutations.

### AI machine credential administration (Batch 1)

These routes are Super Admin-only and administer the machine credentials and
Camera scopes used by final-event ingestion.

| Method | Path | Purpose | Success |
|---|---|---|---|
| GET/POST | `/api/v1/admin/ai-ingestion-credentials/` | List or create credentials | 200/201 |
| GET | `/api/v1/admin/ai-ingestion-credentials/{id}/` | Retrieve safe credential metadata | 200 |
| POST | `/api/v1/admin/ai-ingestion-credentials/{id}/rotate/` | Replace and return a one-time secret | 200 |
| POST | `/api/v1/admin/ai-ingestion-credentials/{id}/revoke/` | Permanently revoke a credential | 200 |
| POST | `/api/v1/admin/ai-ingestion-credentials/{id}/scopes/` | Add/reactivate a Camera scope | 201 |
| DELETE | `/api/v1/admin/ai-ingestion-credentials/{id}/scopes/{camera_id}/` | Deactivate a Camera scope | 200 |

Create and rotate are the only responses containing `secret`. List, detail,
revoke, and scope responses never serialize the secret hash or plaintext
secret. External services use `Authorization: AIKey <key_id>:<secret>` only on
endpoints that explicitly enable machine authentication.

### CameraEvent final-event API (Batch 2)

| Method | Path | Authentication and purpose | Success |
|---|---|---|---|
| POST | `/api/v1/camera-events/` | Machine credential; idempotently create one final event and optional alert | 201/200 |
| PATCH | `/api/v1/camera-events/{id}/` | Originating scoped machine; update continued-observation fields | 200 |
| GET | `/api/v1/camera-events/` | Human JWT; Super Admin globally or Security Officer by assigned Facility | 200 |
| GET | `/api/v1/camera-events/{id}/` | Human JWT with the same Facility scope | 200 |
| GET | `/api/v1/camera-events/{id}/snapshot/` | Human JWT with Facility-authorized protected download | 200 |

Machine input cannot provide Facility, alert severity, alert workflow, or
Incident fields. Fire, smoke, intrusion, unauthorized vehicle, and tamper
events create one SecurityAlert atomically; authorized vehicle events do not.
`source_event_id` is unique per ingestion credential. PATCH cannot change event
identity or human workflow and does not create repeated alerts or semantic
creation audits. Raw detections and AI inference remain outside Django. The
independent Channels and Notification/FCM consumers act only after this API has
persisted final domain state.

POST requiredness is event-specific:

| Event | Required final-event fields beyond `event_type` |
|---|---|
| `fire_alert` | `camera_id`, `source_event_id`, `roi_id`, `track_id`, `class=fire`, `confidence`, `bbox`, `detected_at`, `confirmed_at`, `duration_seconds`, `snapshot_path` |
| `smoke_alert` | `camera_id`, `source_event_id`, `roi_id`, `track_id`, `class=smoke`, `confidence`, `bbox`, `detected_at`, `confirmed_at`, `duration_seconds`, `snapshot_path` |
| `intrusion_alert` | `camera_id`, `source_event_id`, `roi_id`, `track_id`, `class=person`, `confidence`, `bbox`, `entered_roi_at`, `confirmed_at`, `duration_seconds`, `time_restricted=true`, `snapshot_path` |
| `vehicle_entry` / `vehicle_exit` | `camera_id`, `source_event_id`, `track_id`, `plate_number`, `plate_confidence`, `ocr_confidence`, `vehicle_type`, `vehicle_confidence`, matching `direction`, `crossing_centroid`, `authorized`, `bbox_plate`, `bbox_vehicle`, `detected_at`, `snapshot_path`; an active camera VirtualLine is required and authorization is derived and verified against the server registry |
| `tamper_alert` | `camera_id`, `source_event_id`, `tamper_type`, `detected_at`, `confidence`; `snapshot_path` is optional |

PATCH accepts only `confidence`, `bbox`, `duration_seconds`, `confirmed_at`, and
`snapshot_path`. Snapshot values are private storage-relative keys under
`security/camera-events/{facility_uuid}/{camera_uuid}/`; neither REST nor the
WebSocket exposes that key as a public URL.

### AI camera configuration API (Batch 3)

Collection/detail configuration routes use human JWT for Super Admin-only
create, update, and soft-disable operations. GET also accepts an AIKey and
returns active records only for the credential's active cameras and
facilities. Machine credentials cannot mutate configuration.

| Method | Path | Purpose | Success |
|---|---|---|---|
| GET/POST | `/api/v1/roi/` | Read scoped ROIs or create an ROI as Super Admin | 200/201 |
| GET/PUT/PATCH/DELETE | `/api/v1/roi/{id}/` | Read, update, or soft-disable an ROI | 200/204 |
| GET/POST | `/api/v1/restricted-schedules/` | Read scoped schedules or create one per ROI | 200/201 |
| GET/PUT/PATCH/DELETE | `/api/v1/restricted-schedules/{id}/` | Read, update, or soft-disable a schedule | 200/204 |
| GET/POST | `/api/v1/virtual-lines/` | Read scoped lines or create one per camera | 200/201 |
| GET/PUT/PATCH/DELETE | `/api/v1/virtual-lines/{id}/` | Read, update, or soft-disable a line | 200/204 |
| GET/POST | `/api/v1/vehicles/authorized/` | Machine authorization lookup/list or Super Admin registry creation | 200/201 |
| GET/PUT/PATCH/DELETE | `/api/v1/vehicles/authorized/{id}/` | Super Admin registry maintenance | 200/204 |
| GET/POST | `/api/v1/cameras/{camera_id}/active-models/` | Read enabled models or enable one as Super Admin | 200/201 |
| DELETE | `/api/v1/cameras/{camera_id}/active-models/{model_identifier}/` | Soft-disable one model assignment | 204 |

ROI and virtual-line coordinates are unmodified non-negative pixel values.
Schedules use IANA `timezone_name`, `days_of_week` values `0=Monday` through
`6=Sunday`, and local start-day semantics for overnight windows. Plates are
trimmed and uppercased only; expiration is inclusive through `expires_on`.
Configuration describes current/future AI processing and never rewrites a
historical CameraEvent. AI inference remains external to Django.

### Live security WebSocket (Batch 4)

`/ws/security/events/` accepts human JWT access tokens only through the
WebSocket subprotocol list `sflms.jwt`, then token. It rejects query-string
tokens, AIKey credentials, inactive users, and roles without Security view
access. Super Admin receives all live Security events; Security Officers
receive only events for current active Facility assignments.

The version-1 server-to-client message types are
`security.camera_event.created` and `security.alert.updated`. Clients use REST
for initial state and cannot subscribe, mutate domain state, or request replay
over the socket. See `notifications.md` for the exact bounded payload.

### Mobile push device API (Batch 5)

| Method | Path | Authentication and purpose | Success |
|---|---|---|---|
| GET/POST | `/api/v1/notifications/devices/` | Human JWT; list own devices or idempotently register a write-only FCM token | 200/201 |
| GET/PATCH/DELETE | `/api/v1/notifications/devices/{id}/` | Human JWT; retrieve/update or soft-disable own device only | 200/204 |

Accepted platforms are `android` and `ios`. Device responses never serialize
the registration token or its hash. AIKey, anonymous, roleless-machine, and
cross-user device access are rejected. This API does not accept alert,
recipient, Facility, severity, payload, or FCM-delivery controls.

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
| POST | `/api/v1/reports/requests/{id}/retry/` | Requeue an owner-visible failed report and clear the prior failure | 202 |

Facility list/detail responses include the server-aggregated `asset_count`; the
frontend must not issue one monitoring request per facility. Operational
monitoring is exposed internally at `GET /metrics/` in Prometheus text format.

Construction Managers may request `construction`, Operations Managers may
request `assets` and `maintenance`, and Security Officers may request
`security`. Super Admin may request every model-supported module, including
`materials`. Request creation calls the existing report service and dispatches
the existing Celery task; generation never runs synchronously in the API.
Queued/processing/failed reports have no downloadable output.

### External Safety Alerts API

Human JWT only; machine `AIKey` credentials and roleless principals are
rejected. Access requires an active Super Admin, Construction Manager, or
Operations Manager holding `safety.view` (Super Admin bypasses permission
checks); workflow actions also require `safety.manage`. Security Officers
receive 403 even if a Safety permission is granted.

Scope is derived only from the authenticated user: Construction Managers see
projects with their active `ProjectAssignment`; Operations Managers see
projects whose active facility has their active `FacilityAssignment`; Super
Admin sees all. Out-of-scope records return 404, and filters only narrow the
scoped result.

| Method | Path | Purpose | Success |
|---|---|---|---|
| GET | `/api/v1/safety/alerts/` | Scoped, paginated project safety alerts | 200 |
| GET | `/api/v1/safety/alerts/{id}/` | Retrieve a scoped alert | 200 |
| POST | `/api/v1/safety/alerts/{id}/acknowledge/` | `new → acknowledged` (empty body) | 200 |
| POST | `/api/v1/safety/alerts/{id}/decide/` | `acknowledged/actioned → actioned` with `decision` and optional `notes` | 200 |
| POST | `/api/v1/safety/alerts/{id}/dismiss/` | `new/acknowledged → dismissed` with required `reason` | 200 |
| POST | `/api/v1/safety/alerts/{id}/close/` | `actioned → closed` with optional `notes` | 200 |
| GET | `/api/v1/safety/hazard-events/` | Scoped, paginated normalized hazard events | 200 |
| GET | `/api/v1/safety/hazard-events/{id}/` | Retrieve a scoped hazard event | 200 |
| GET | `/api/v1/safety/monitoring-coverage/` | Scoped counts of monitored projects with/without coordinates, plus whether alert creation is enabled | 200 |

Alert responses contain the alert state, a project summary (`id`, `name`,
`location`, `status`, `facility_id`), the nested hazard event, `distance_km`,
the project coordinate snapshot, `rule_code`, `policy_version`,
`recommended_action`, decision and resolution fields with actor summaries
(`id`, `full_name`), `hazard_withdrawn_at`, `escalated_at`, and
`available_actions`. `available_actions` is calculated by the server from the
workflow state machine and is empty when the caller lacks `safety.manage`.
Hazard event responses contain the normalized provider fields; the raw provider
payload and `last_seen_at` are never serialized. Decimal values are strings.

Filters — alerts: `project`, `severity`, `status`, `hazard_type`, `provider`,
`hazard_withdrawn`, `created_after`, `created_before`, `search` (project name,
hazard title), `ordering` (`created_at`, `updated_at`, `distance_km`; default
`-created_at`). Hazard events: `provider`, `hazard_type`, `alert_level`,
`provider_status`, `project` (in-scope projects only), `occurred_after`,
`occurred_before`, `search` (title), `ordering` (`occurred_at`,
`provider_updated_at`, `created_at`; default `-occurred_at`). Hazard events have
no severity field; `alert_level` and `provider_severity` carry provider
severity. Invalid choices, UUIDs, timestamps, or a reversed date range return
400. Pagination uses the standard envelope (`page_size` up to 100).

Action request bodies reject unknown fields with 400, so clients cannot set
status, severity, project, hazard event, provider, distance, coordinates,
policy fields, actors, or timestamps. Input shape errors return 400; transitions
refused by the Safety workflow service (wrong state, `other` without notes,
another user's acknowledgement) return 409 `DomainConflict`, matching the
Security alert API. Missing `safety.manage` returns 403. Actions call
`apps.safety.services` only, which records the semantic `safety_alert.*` audit
entry; the API creates no notifications. Withdrawn alerts remain actionable.
There are no create, update, delete, or ingestion endpoints for hazard events
or alerts; ingestion stays inside the provider polling pipeline.

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
