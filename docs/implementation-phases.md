# Implementation Phases

## Purpose
The complete roadmap from Phase 1 through production, with objectives,
tasks, dependencies, deliverables, completion criteria, testing
requirements, and documentation-update requirements per phase.

## Scope
Sequencing and scope per phase. What each phase *builds* in domain detail
is specified in the relevant `docs/` files (referenced per phase below),
not repeated here.

## Architecture

### Phase 1 — Foundation ✅ COMPLETE (frozen — see `docs/reports/PHASE1_FORWARD_COMPATIBILITY_AUDIT.md`)
- **Objectives**: project skeleton, custom User model, RBAC foundation, JWT auth, Swagger.
- **Deliverables**: `config/`, `apps/common`, `apps/users`, `apps/authentication`; 3 models; full test suite.
- **Completion criteria**: all met — see `docs/reports/PHASE1_VERIFICATION_REPORT.md`.
- **Documentation updates**: this entire `docs/` system, created after Phase 1 code.

### Phase 2 — Docker & Infrastructure (completed and runtime verified)
- **Objectives**: production-oriented Docker-first environment and operational
  foundations only. Attachment/domain work is explicitly excluded from this phase.
- **Tasks**: `Dockerfile`, `docker-compose.yml` (+ override for development),
  `.dockerignore`, entrypoint/readiness scripts, health endpoints, PostgreSQL,
  Redis cache, Celery Worker/Beat, Channels/ASGI foundation, persistent volumes,
  environment/logging/static/media configuration, and Docker-only onboarding.
- **Dependencies**: none beyond Phase 1.
- **Deliverables**: `docker compose up` starts `backend`, `postgres`, `redis`,
  `celery_worker`, and `celery_beat`; liveness/dependency endpoints are healthy.
- **Completion criteria**: a fresh clone follows `onboarding.md`; all containers
  start; Django checks, migration drift check, and pytest pass inside Docker.
- **Testing requirements**: `docker compose exec backend pytest` passes inside
  the container; infrastructure tests verify settings, health, Celery, Redis,
  and Compose assumptions.
- **Documentation updates**: Docker, environment, deployment, testing,
  monitoring, onboarding, folder structure, known limitations, roadmap, and logs.
- **Scope note**: ADR-0013 remains approved, but Attachment implementation is
  deferred. It must be scheduled before Construction features that depend on it.

### Phase 3 — Construction Domain
- **Objectives**: `projects`, `construction`, `materials` apps, fully implementing `business-domain.md` §Construction Lifecycle.
- **Tasks**: models, migrations, serializers, views, `ProjectAssignment`, `permissions.py` (Layer 2 object-level filtering begins here), `services.py` (`convert_project_to_facility` — depends on `facilities` existing, see dependency note below).
- **Dependencies**: Phase 2 infrastructure plus a separately approved Attachment
  implementation (`ProjectDocument` depends on it); **note** — `Project.facility`
  FK requires the `facilities` app to exist for its migration to apply (see
  `docs/reports/PHASE1_FORWARD_COMPATIBILITY_AUDIT.md` §6) — either Phase 3 and 4 ship together,
  or `Project.facility` is added via a later migration once Phase 4 lands. Decide
  explicitly at Phase 3 kickoff, don't default silently.
- **Deliverables**: full Construction Lifecycle API surface.
- **Completion criteria**: Workflow 1/2 in `project-workflows.md` pass as integration tests.
- **Documentation updates**: `database-design.md`, `database-erd.md`, `api-specification.md` (per-app sections), `permissions-rbac.md` (Layer 2 examples).

### Phase 4 — Operations Domain
- **Objectives**: `facilities`, `assets`, `maintenance` apps.
- **Tasks**: models, migrations, `FacilityAssignment`, `AssetHealthHistory`, `MaintenanceOrder`/`WorkExecutionLog` split (ADR-0015), `MaintenanceChecklist`, `MaintenanceCalendarEvent`, `Fault`/`FaultTimeline`.
- **Dependencies**: resolves the Phase 3 `facilities` dependency noted above.
- **Completion criteria**: Workflow 3 in `project-workflows.md` passes as an integration test.
- **Documentation updates**: same set as Phase 3, plus `celery-tasks.md` (`check_maintenance_calendar` moves from specified to implemented — partially, since it's still Phase 6+ for full Celery wiring).

### Phase 5 — Security Domain (manual entry, no AI yet)
- **Objectives**: `security` app — `Camera`, `SecurityAlert`, `Incident`, `IncidentAction` — with manual/API-driven Alert creation, deliberately before AI wiring, to validate the workflow independent of AI reliability.
- **Dependencies**: Phase 4 (`FacilityAssignment`).
- **Completion criteria**: Workflow 4 in `project-workflows.md` passes end-to-end using manually-created Alerts (no camera/YOLO involved yet).
- **Documentation updates**: same set as prior phases.

### Phase 6 — AI Engine
- **Objectives**: external-AI integration contracts only; Django does not run AI inference.
- **Tasks**: roleless AIKey authentication, camera scopes, final CameraEvent ingestion, and current camera/ROI/schedule/line/vehicle/model configuration APIs.
- **Dependencies**: Phase 5 Security models.
- **Completion criteria**: authenticated external services can read scoped configuration and persist idempotent final events that conditionally create SecurityAlerts.
- **Documentation updates**: `ai-engine.md`, `camera-processing.md`, and `authentication.md`.

### Phase 7 — Real-Time Layer
- **Objectives**: Django Channels delivery of committed final security events.
- **Tasks**: `/ws/security/events/`, JWT subprotocol authentication, server-owned recipient scoping, stable payloads, and transaction-safe broadcasts.
- **Dependencies**: persisted CameraEvent/SecurityAlert contracts and the existing Redis channel layer.
- **Completion criteria**: authorized human clients receive scoped live events after commit; AIKey, invalid roles, and cross-facility access are rejected.
- **Documentation updates**: `notifications.md`, `authentication.md`, and ADR-0010.

### Phase 8 — Reporting
- **Objectives**: `reports` app, PDF/Excel generation.
- **Tasks**: resolve the PDF library choice in `reporting.md` §Future Evolution, `ReportTemplate`, async generation via Celery.
- **Dependencies**: enough domain data to report on (Phases 3–6).
- **Completion criteria**: a report requested via API completes asynchronously and produces a downloadable file.
- **Documentation updates**: `reporting.md`, `celery-tasks.md`.

### Phase 9 — Audit & Hardening
- **Objectives**: `audit` app; full security review.
- **Tasks**: `AuditLog`, signal-based or middleware-based capture (per `coding-standards.md` §Signals rules), rate limiting on `/api/auth/login/` (see `security.md` §Future Evolution), dependency vulnerability scanning.
- **Dependencies**: ideally after all domain apps exist, so audit coverage is comprehensive from the start rather than retrofitted per app.
- **Completion criteria**: every create/update/delete/login/permission-denied event across every implemented app produces an `AuditLog` row.
- **Documentation updates**: `security.md` (flip Audit logging to implemented).

### Phase 10 — Integration Testing & Production Readiness
- **Objectives**: full end-to-end verification against the real (Docker) frontend; performance baseline measurement; backup/restore implementation and testing.
- **Tasks**: execute and document a real test restore (`backup-recovery.md` §Future Evolution), establish real performance numbers (`performance.md` §Query budget), health-check endpoints wired into Compose (`monitoring-observability.md`), CI/CD pipeline (`deployment.md` §Future Evolution).
- **Dependencies**: all prior phases.
- **Completion criteria**: production deployment checklist (to be written as part of this phase) fully green.
- **Documentation updates**: `backup-recovery.md`, `performance.md`, `deployment.md`, `security.md` — all flip their remaining open items to resolved/implemented.

## Business Rules
N/A.

## Technical Notes
Phase numbers are sequencing, not calendar commitments — no phase starts
before its stated dependencies are met, but phases may be reordered if a
dependency is resolved differently than planned (e.g., if Phase 3/4 ship
together to resolve the Project/Facility circular dependency cleanly).

## Current Implementation
Phase 1 complete and frozen. Phase 2 implementation is present; its completion
status remains pending until Docker runtime checks and the full test suite pass.
All domain phases remain unstarted.

## Future Evolution
This document is updated at the start and end of every phase: objectives
refined at start if reality diverges from this plan, completion status
and any discovered follow-up work recorded at end.

## Important Decisions
Security domain (Phase 5) ships before AI (Phase 6) deliberately — so the
manual workflow is proven correct before AI reliability becomes a
variable in debugging it.

## Developer Notes
Before starting a phase, re-read its full dependency list above — several
phases have non-obvious cross-app dependencies (see Phase 3's note on
`facilities`).

## Related Components
`development-roadmap.md`, `decision-log.md`, every domain document
referenced per phase above.

## Files Involved
Spans the entire repository over time.

## Dependencies
`business-domain.md`, `system-architecture.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
Phase completion status — marking a phase complete without its
completion criteria genuinely met is the single most damaging
documentation error possible in this system (future sessions will trust
it and build on false assumptions).

## Future Improvements
Add calendar/effort estimates once a team is actually resourced against
this roadmap — deliberately omitted now to avoid a fabricated timeline.
