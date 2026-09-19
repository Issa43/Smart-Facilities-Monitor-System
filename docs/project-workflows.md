# Project Workflows

## Purpose
Step-by-step operational sequences for the system's key multi-stage
processes — the "how a user actually moves through this" view that
complements `business-domain.md`'s rule-first view.

## Scope
Cross-endpoint, cross-model workflows. Individual endpoint contracts are
`api-specification.md`; the rules each step must obey are
`business-domain.md`.

## Architecture

### Workflow 1 — Construction → Facility conversion
```
1. Super Admin creates Project through the current API (status=Planning)
2. Construction Manager (via ProjectAssignment) manages Phases,
   DailyReports, Materials as work progresses
3. Final Phase reaches current_progress=100 → Project manually
   transitioned to status=Completed (not automatic)
4. Authorized user calls the conversion action
   (POST /api/v1/projects/{id}/convert-to-facility/)
5. services.convert_project_to_facility() runs:
   a. Creates Facility row
   b. Sets Facility.created_from_project = this Project
   c. Sets Project.facility = the new Facility
   d. Project.status → Operational
6. Facility now exists independently — Operations/Security lifecycles
   can begin (Asset registration, Camera setup, FacilityAssignment)
```

### Workflow 2 — Facility expansion (existing facility, new project)
```
1. User creates a new Project with facility = <existing Facility id>
   set directly at creation (never null → converted later)
2. This Project follows the normal Phase/DailyReport/Material workflow
3. On completion, NO conversion step runs — Facility.created_from_project
   still points to the original genesis Project, unchanged
```

### Workflow 2A — Construction Material Request approval
```
1. An assigned Construction Manager creates a Material Request (Submitted)
2. Super Admin globally retrieves and reviews the request
3. Super Admin approves it (Reviewed -> Approved), or rejects it (Rejected)
4. An Approved request may continue through the existing completion flow
```
Construction Managers, Operations Managers, and Security Officers cannot
review, approve, or reject Construction Material Requests. Project assignment
scoping still controls Construction Manager visibility; Super Admin is global.

### Workflow 3 — Maintenance request to resolution
```
1. Fault reported (manually, or from Asset health monitoring) →
   status=Reported
2. Assigned engineer investigates → status=Investigating
3. If work is needed: MaintenanceOrder created (type=Corrective or
   Emergency), optionally linked to the Fault
4. MaintenanceOrder assigned (status=Assigned) → work begins
   (status=In Progress)
5. One or more WorkExecutionLog rows record actual work sessions
   (a single Order may need several attempts/technicians)
6. MaintenanceChecklist items marked complete as work proceeds
7. MaintenanceOrder → status=Completed → Closed
8. Fault (if linked) → status=Resolved → Closed, with root_cause/
   resolution filled in
```

### Workflow 4 — Security detection to incident closure
```
1. Camera streams frames → AI Engine produces CameraDetectionEvent(s)
2. Deduplication/threshold logic creates a SecurityAlert (or attaches to
   an existing open one) — see ai-engine.md
3. Durable per-recipient Notifications are created for eligible assigned
   Security Officers and active Super Admins; per-device FCM delivery is
   queued after commit, while live dashboard delivery independently uses Channels
4. Security Officer reviews the Alert:
   a. Genuine → POST /api/v1/security/alerts/{id}/convert-to-incident/
      → Incident created (Incident.alert = this Alert),
        Alert.status = Converted
   b. False positive → Alert marked is_false_positive=True with
      review_notes, Alert.status = Dismissed
5. If an Incident was created: IncidentAction rows log the response
   (containment, notification, escalation...) as the Security Officer
   works it
6. Incident → status=Investigation → (optionally Transferred) → Closed,
   with final_report and closed_by filled in
```

### Workflow 5 — Login to authenticated request (cross-cutting)
```
1. POST /api/v1/auth/login/ → access + refresh tokens (see authentication.md)
2. Every subsequent request: Authorization: Bearer <access>
3. On 401 (access expired): POST /api/v1/auth/refresh/ → new access
   (+ rotated refresh) → retry original request
4. On logout: POST /api/v1/auth/logout/ { refresh } → refresh blacklisted
```

## Business Rules
Each workflow above is a sequencing constraint on top of the rules already
stated in `business-domain.md` — this document does not introduce new
rules, only orders the existing ones.

## Technical Notes
Workflow steps that cross models (step 5 in Workflow 1, step 2 in
Workflow 4) are implemented as `services.py` functions, never as
serializer `save()` overrides or view-method-only logic — see
`coding-patterns.md` §Service Layer.

## Current Implementation
The Phase 3 service layer implements Project completion and Facility
conversion, maintenance and fault transitions, SecurityAlert/Incident
workflows, and authentication. Phase 4 exposes the corresponding versioned
Project, phase, Operations, and Security actions documented in
`api-specification.md`.

Workflow 3's `WorkExecutionLog` and `MaintenanceChecklist` steps remain future
scope and are not exposed by the current API. Workflow 4's external inference
remains outside Django; final CameraEvent ingestion, SecurityAlert creation,
durable Notification/FCM delivery, live Channels delivery, and downstream
review/Incident response are implemented. Workflow 1's DailyReport, Material, MaterialRequest,
QualityInspection, ProjectDocument, and SitePhoto records are exposed through
the assignment-scoped `/api/v1/construction/` API.

## Future Evolution
As each workflow is implemented, verify its actual code path against the
sequence documented here — if implementation reveals a missing or
reordered step, update this document in the same PR.

## Important Decisions
Manual (not automatic) Project→Facility conversion (ADR-0014).
MaintenanceOrder/WorkExecutionLog separation allowing multiple execution
attempts (ADR-0015).

## Developer Notes
When implementing any of these workflows, write an integration test that
exercises the *entire* sequence end-to-end (not just each endpoint in
isolation) — see `testing.md` §Integration Testing.

## Related Components
`business-domain.md`, `ai-engine.md`, `authentication.md`,
`api-specification.md`.

## Files Involved
Spans every domain app once implemented.

## Dependencies
`glossary.md`, `business-domain.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
The manual conversion step in Workflow 1. The dedup-then-alert ordering
in Workflow 4.

## Future Improvements
Add sequence diagrams (not just ASCII) once a diagramming tool is adopted
for the docs system.
