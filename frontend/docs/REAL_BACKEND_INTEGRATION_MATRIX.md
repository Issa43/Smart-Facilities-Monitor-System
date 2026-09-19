# SFLMS real-backend integration matrix

This document is the implementation ledger for the existing 60-route frontend.
The UI and route tree are preserved. The Django API is authoritative for fields,
enums, lifecycle actions, authorization, and protected files.

Status vocabulary:

- **CONNECTED**: uses the real API.
- **SUPPORTED / PENDING**: the backend contract exists; frontend wiring remains.
- **API GAP**: the backend domain exists but the required frontend endpoint does not.
- **DOMAIN GAP**: the required model/service/domain does not exist.
- **FRONTEND-ONLY**: no backend operation is required.
- **DEFERRED**: UI is preserved and must report unavailability honestly.

All real endpoints require JWT authentication unless noted. Role guards below are
UX controls only; backend RBAC remains authoritative. List endpoints use the shared
paginated envelope and supported query parameters (`page`, filters, `search`, and
`ordering`).

## Core and authentication

| Route                     | Screen / feature            | Backend contract                             | RBAC                                   | Status                       |
| ------------------------- | --------------------------- | -------------------------------------------- | -------------------------------------- | ---------------------------- |
| `/`                       | Role-aware home redirect    | `GET /users/me/`                             | Authenticated                          | CONNECTED                    |
| `/login`                  | Email/password login        | `POST /auth/login/`, `GET /users/me/`        | Public login                           | CONNECTED                    |
| `/forgot-password`        | Request reset email         | None                                         | Public, enumeration-safe flow required | DOMAIN GAP / DEFERRED        |
| `/reset-password`         | Complete password reset     | None                                         | One-time reset token required          | DOMAIN GAP / DEFERRED        |
| `/reset-password/success` | Reset confirmation          | None                                         | Frontend-only result screen            | DEFERRED with reset workflow |
| `/profile`                | View/update profile, logout | `GET/PATCH /users/me/`, `POST /auth/logout/` | Authenticated self                     | CONNECTED                    |
| `/help`                   | Static help and guidance    | None                                         | Authenticated                          | FRONTEND-ONLY                |
| `*`                       | Not-found screen            | None                                         | Public                                 | FRONTEND-ONLY                |

## Super Admin

| Route                             | Screen / feature                        | Backend contract                                                | RBAC                                       | Status                                                             |
| --------------------------------- | --------------------------------------- | --------------------------------------------------------------- | ------------------------------------------ | ------------------------------------------------------------------ |
| `/admin/dashboard`                | Project/user/incident KPIs and activity | composable scoped APIs                                          | Super Admin                                | CONNECTED current totals; trends and audit feed are gaps           |
| `/admin/projects`                 | Project list/search/filter/order        | `GET /projects/`, assignments                                   | Super Admin                                | CONNECTED; client controls consume real paginated records          |
| `/admin/projects/new`             | Create project                          | `POST /projects/`                                               | Super Admin                                | CONNECTED, including multipart image and assignment                |
| `/admin/projects/:projectId`      | Project detail, assignments, lifecycle  | detail, assignments, `start`, `complete`, `convert-to-facility` | Super Admin                                | CONNECTED; unsupported subdomains show gap warning                 |
| `/admin/projects/:projectId/edit` | Update project metadata                 | `PATCH /projects/{id}/`                                         | Super Admin                                | CONNECTED; deletion is API GAP and fails honestly                  |
| `/admin/users`                    | List/create/filter users                | `GET/POST /users/`, `GET /users/roles/`                         | Super Admin                                | CONNECTED; server-query UI pending                                 |
| `/admin/users/:userId`            | Retrieve/status/delete user             | `GET/PATCH/DELETE /users/{id}/`                                 | Super Admin                                | CONNECTED; forced reset and audit are gaps                         |
| `/admin/roles`                    | Role catalogue/matrix                   | `GET /users/roles/`                                             | Super Admin screen; endpoint authenticated | CONNECTED read-only                                                |
| `/admin/reports`                  | Requests, polling, download             | `/reports/requests/`, `/download/`                              | Super Admin                                | CONNECTED; user reports are outside backend modules                |
| `/admin/analytics`                | Cross-domain charts                     | real scoped list APIs                                           | Super Admin bypass                         | CONNECTED current totals; historical trends remain empty (API GAP) |
| `/admin/notifications`            | Notification centre                     | None                                                            | User-owned notifications required          | DOMAIN GAP / DEFERRED                                              |
| `/admin/audit-logs`               | Audit log table                         | None                                                            | Super Admin or explicitly scoped readers   | DOMAIN GAP / DEFERRED                                              |
| `/admin/settings`                 | Persistent system settings/demo reset   | None                                                            | Super Admin                                | DOMAIN GAP / DEFERRED; demo reset development-only                 |

## Construction Manager

| Route                                 | Screen / feature                            | Backend contract                                                                 | RBAC                                        | Status                                               |
| ------------------------------------- | ------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------- | ---------------------------------------------------- |
| `/construction/dashboard`             | Assigned-project and phase summary          | Phase monitoring requires a known project                                        | Assigned Construction Manager               | API GAP: scoped project discovery blocks integration |
| `/construction/projects`              | Assigned project list                       | No scoped Project list/detail endpoint                                           | Assigned Construction Manager               | API GAP                                              |
| `/construction/projects/:projectId`   | Project detail and phases                   | Phase routes exist; Project detail does not                                      | Assigned Construction Manager / Super Admin | API GAP with partially supported phase data          |
| `/construction/stages`                | Phase list/create/search/order              | `GET/POST /projects/{projectId}/phases/`                                         | Assigned Construction Manager / Super Admin | SUPPORTED after scoped-project lookup gap            |
| `/construction/stages/:stageId`       | Phase metadata, progress, histories, review | Phase detail, `progress`, histories, `approve`, `reject`, `request-modification` | Assigned Construction Manager / Super Admin | SUPPORTED after scoped-project lookup gap            |
| `/construction/progress`              | Progress overview                           | Phase list and `/phases/monitoring/`                                             | Assigned Construction Manager / Super Admin | SUPPORTED after scoped-project lookup gap            |
| `/construction/timeline`              | Project/phase schedule                      | Project and phase list APIs                                                      | Assigned Construction Manager               | API GAP for project discovery                        |
| `/construction/materials`             | Inventory and consumption                   | Domain models/services exist; no API                                             | Assigned Project scope required             | API GAP                                              |
| `/construction/material-requests`     | Request list/review lifecycle               | Domain models/services exist; no API                                             | Assigned Project scope required             | API GAP                                              |
| `/construction/material-requests/new` | Create material request                     | Domain exists; no API                                                            | Assigned Project scope required             | API GAP                                              |
| `/construction/quality`               | Quality inspections                         | No approved domain/API                                                           | Assigned Project scope required             | DOMAIN GAP / DEFERRED                                |
| `/construction/daily-reports`         | Daily reports and attachments               | Domain exists; no API                                                            | Assigned Project scope required             | API GAP                                              |
| `/construction/documents`             | Upload/list/download project documents      | Domain/protected storage exist; no API                                           | Assigned Project scope required             | API GAP                                              |
| `/construction/photos`                | Site photos                                 | No approved domain/API; protected project image is separate                      | Assigned Project scope required             | DOMAIN GAP / DEFERRED                                |

## Operations Manager

| Route                                | Screen / feature                      | Backend contract                                | RBAC                              | Status                                              |
| ------------------------------------ | ------------------------------------- | ----------------------------------------------- | --------------------------------- | --------------------------------------------------- |
| `/operations/dashboard`              | Scoped operations KPIs                | `GET /operations/monitoring/` plus scoped lists | Assigned Facilities / Super Admin | CONNECTED; historical trend is API GAP              |
| `/operations/facilities`             | Facility list/search/filter/order     | `GET /facilities/`                              | Assigned Facilities / Super Admin | CONNECTED                                           |
| `/operations/facilities/:facilityId` | Facility detail and monitoring        | detail and `/monitoring/`                       | Assigned Facility / Super Admin   | CONNECTED                                           |
| `/operations/assets`                 | Asset list/register                   | `GET/POST /assets/`                             | Assigned Facility / Super Admin   | CONNECTED                                           |
| `/operations/assets/:assetId`        | Asset detail/update/status transition | detail/PATCH and `transition-status/`           | Assigned Facility / Super Admin   | CONNECTED; deletion unsupported                     |
| `/operations/asset-health`           | Asset health monitoring               | real asset list/health fields                   | Assigned Facilities / Super Admin | CONNECTED                                           |
| `/operations/work-orders`            | Maintenance list/create               | `GET/POST /maintenance/orders/`                 | Assigned Facilities / Super Admin | CONNECTED                                           |
| `/operations/work-orders/:orderId`   | Metadata and start/complete/close     | Detail/PATCH plus lifecycle endpoints           | Assigned Facility / Super Admin   | CONNECTED; checklist/notes/cancel are gaps          |
| `/operations/preventive`             | Preventive-order filtered list        | `GET /maintenance/orders/?type=preventive`      | Assigned Facilities / Super Admin | SUPPORTED / PENDING                                 |
| `/operations/corrective`             | Corrective-order filtered list        | `GET /maintenance/orders/?type=corrective`      | Assigned Facilities / Super Admin | SUPPORTED / PENDING                                 |
| `/operations/calendar`               | Scheduled maintenance calendar        | Orders filtered/ordered by execution date       | Assigned Facilities / Super Admin | SUPPORTED / PENDING                                 |
| `/operations/faults`                 | Fault list/create/update/lifecycle    | `/faults/`, `investigate`, `resolve`, `close`   | Assigned Facilities / Super Admin | CONNECTED                                           |
| `/operations/performance`            | Facility/asset performance            | Facility/asset monitoring plus scoped lists     | Assigned Facilities / Super Admin | SUPPORTED / PENDING; time-series trends are API GAP |
| `/operations/reports`                | Operations report requests/downloads  | report requests/download                        | Operations Manager / Super Admin  | CONNECTED                                           |

## Security Officer

| Route                             | Screen / feature                              | Backend contract                                   | RBAC                              | Status                                                                                               |
| --------------------------------- | --------------------------------------------- | -------------------------------------------------- | --------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `/security/dashboard`             | Scoped alerts/incidents summary               | Scoped lists; no dedicated aggregate               | Assigned Facilities / Super Admin | CONNECTED by real-data composition; history metrics are gaps                                         |
| `/security/alerts`                | Alert list/search/filter/order                | `GET /security/alerts/`                            | Assigned Facilities / Super Admin | CONNECTED                                                                                            |
| `/security/alerts/:alertId`       | Review/dismiss/convert/snapshot               | lifecycle and protected snapshot endpoints         | Assigned Facility / Super Admin   | CONNECTED, including mandatory dismissal reason                                                      |
| `/security/alert-history`         | Reviewed/dismissed/converted alerts           | Filtered alert list                                | Assigned Facilities / Super Admin | SUPPORTED / PENDING                                                                                  |
| `/security/incidents`             | Incident list/manual creation                 | `GET/POST /security/incidents/`                    | Assigned Facilities / Super Admin | CONNECTED                                                                                            |
| `/security/incidents/:incidentId` | Investigation/transfer/close/actions/evidence | lifecycle, append-only actions, evidence/downloads | Assigned Facility / Super Admin   | CONNECTED where supported; notes/toggle are honest gaps; transfer blocked by assignee lookup API gap |
| `/security/response`              | Open incident response queue/actions          | Incident list and append-only actions              | Assigned Facilities / Super Admin | SUPPORTED / PENDING; action toggle semantics must become append-only history                         |
| `/security/emergency`             | Critical alert monitoring/manual incident     | Filtered alerts and incident creation              | Assigned Facilities / Super Admin | SUPPORTED / PENDING                                                                                  |
| `/security/cameras`               | Camera monitoring                             | None                                               | Assigned Facility scope required  | DOMAIN GAP / DEFERRED                                                                                |
| `/security/analytics`             | Incident/alert analytics                      | Scoped lists can compose current totals            | Assigned Facilities / Super Admin | PARTIAL; historical analytics are API GAP                                                            |
| `/security/reports`               | Security report requests/downloads            | report requests/download                           | Security Officer / Super Admin    | CONNECTED                                                                                            |
| `/security/documents`             | Facility safety documents                     | No approved safety-document domain/API             | Assigned Facility scope required  | DOMAIN GAP / DEFERRED                                                                                |

## Cross-cutting implementation requirements

| Area              | Required behavior                                                                    | Current status                                                |
| ----------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------- |
| JWT/session       | Session storage, refresh-on-401, logout on refresh failure                           | CONNECTED                                                     |
| Error model       | Normalize network and backend error envelopes without fake success                   | CONNECTED; screen-level coverage pending                      |
| Pagination        | Consume the full envelope; expose page/filter/search/order parameters to list UIs    | Foundation connected; screen wiring pending                   |
| Protected files   | Authenticated Blob download; never expose storage paths                              | CONNECTED for alert snapshots, incident evidence, and reports |
| Reports           | Respect `202 Accepted`, poll queued/processing state, download only completed output | CONNECTED                                                     |
| Fixture database  | Never run when `VITE_ENABLE_DEMO_DATA=false`                                         | ISOLATED; mocked domain modules still need replacement        |
| UI preferences    | Sidebar collapse and list/card view may remain in `localStorage`                     | FRONTEND-ONLY                                                 |
| Dashboard metrics | Real monitoring/list sources only; unavailable metrics render honestly               | CONNECTED current metrics; historical series are API GAP      |

## Backend enum mismatches requiring explicit reconciliation

- Project/Facility type: frontend demo categories do not match backend
  `commercial/residential/industrial/healthcare/education/government/mixed_use/other`.
- Project status: frontend includes `on_hold`; backend does not.
- Phase status: backend uses `needs_modification`; frontend uses `under_review`.
- Phase priority: backend has `low/medium/high`; frontend additionally uses `critical`.
- Facility status: backend has `decommissioned`; frontend has `partial`.
- Asset status: frontend has `needs_maintenance`; backend does not.
- Maintenance type adds backend `emergency`; priority uses backend `urgent` rather
  than frontend `critical`; status adds `assigned/closed` and has no cancellation.
- Fault severity uses backend `minor/moderate/major/critical`; status has no
  frontend `repairing` and adds `closed`.
- Alert status uses backend `reviewed/converted`; frontend uses
  `acknowledged/escalated`.
- Incident status uses backend `open/investigation/transferred/closed`; frontend
  uses `new/investigating/action_required/resolved/closed`.

Adapters and UI option sets must follow these authoritative backend values; lifecycle
state must never be written through ordinary PATCH requests.
