# SFLMS Engineering Documentation

This directory is the **permanent engineering memory** of the Smart Facility
Lifecycle Management System (SFLMS) backend. Any future Claude Code session,
or any human developer joining the project, must be able to understand the
entire system by reading these documents — without asking anyone to
re-explain the project.

**Rule:** documentation is part of the codebase. If an implementation change
contradicts a document, the document is either updated in the same change,
or the change is wrong. Never let drift accumulate.

**Rule:** this repository is Docker-first from day one. There is no
supported local (non-containerized) execution path. Every document in this
directory assumes Docker Compose as the runtime environment unless
explicitly stated otherwise.

---

## How to read this directory (in order, for a new session/developer)

1. **Orientation** — understand what the system is and who uses it
   - [`project-overview.md`](./project-overview.md) — what SFLMS is, who uses it, high-level lifecycle
   - [`business-domain.md`](./business-domain.md) — the five lifecycles (Construction, Operations, Maintenance, Security, AI) and how they connect
   - [`glossary.md`](./glossary.md) — precise definitions of every domain term used across all other docs

2. **Architecture** — understand how the system is built
   - [`system-architecture.md`](./system-architecture.md) — the full stack, container topology, data flow
   - [`backend-architecture.md`](./backend-architecture.md) — Django app structure, layering (API/Service/Data)
   - [`folder-structure.md`](./folder-structure.md) — literal directory tree and what belongs where

3. **Data**
   - [`database-design.md`](./database-design.md) — every model, field, relationship, constraint
   - [`database-erd.md`](./database-erd.md) — entity-relationship diagram and cross-module map

4. **API & Access Control**
   - [`api-specification.md`](./api-specification.md) — every endpoint, request/response, status
   - [`authentication.md`](./authentication.md) — JWT flow, access/refresh tokens
   - [`permissions-rbac.md`](./permissions-rbac.md) — the 4 roles, RBAC + object-level permission design

5. **Domain Engines**
   - [`ai-engine.md`](./ai-engine.md) — YOLO/OpenCV pipeline, detection → alert → incident
   - [`camera-processing.md`](./camera-processing.md) — RTSP ingestion, frame capture, recordings
   - [`notifications.md`](./notifications.md) — independent Channels live events and durable recipient notifications
   - [`reporting.md`](./reporting.md) — PDF/Excel generation architecture
   - [`project-workflows.md`](./project-workflows.md) — construction → facility conversion, maintenance workflow, incident workflow

6. **Engineering Practice**
   - [`coding-standards.md`](./coding-standards.md) — naming, style, review rules
   - [`coding-patterns.md`](./coding-patterns.md) — canonical implementation patterns (service layer, ViewSets, etc.)
   - [`testing.md`](./testing.md) — test strategy and layout
   - [`performance.md`](./performance.md) — performance budget and known bottleneck strategy
   - [`security.md`](./security.md) — security posture beyond auth (input validation, secrets, OWASP)

7. **Infrastructure**
   - [`docker.md`](./docker.md) — full Docker Compose architecture
   - [`environment.md`](./environment.md) — every environment variable, per service
   - [`deployment.md`](./deployment.md) — how the system ships, dev → production
   - [`monitoring-observability.md`](./monitoring-observability.md) — logging, health checks, metrics
   - [`backup-recovery.md`](./backup-recovery.md) — backup cadence and restore procedure

8. **Operational References**
   - [`celery-tasks.md`](./celery-tasks.md) — the authoritative Celery task registry
   - [`onboarding.md`](./onboarding.md) — zero-to-running-system for a new developer

9. **Planning & History**
   - [`implementation-phases.md`](./implementation-phases.md) — Phase 1 → production roadmap with completion criteria
   - [`development-roadmap.md`](./development-roadmap.md) — near-term execution plan and sequencing
   - [`decision-log.md`](./decision-log.md) — narrative log of major technical decisions
   - [`adr/`](./adr/) — formal Architecture Decision Records, one per major decision
   - [`known-limitations.md`](./known-limitations.md) — current, deliberate gaps
   - [`future-roadmap.md`](./future-roadmap.md) — post-production evolution ideas
   - [`change-log.md`](./change-log.md) — chronological record of what actually changed and when

---

## Document contract

Every document in this directory (except this index and the ADR records,
which follow their own fixed format) contains these sections, in order:

`Purpose · Scope · Architecture · Business Rules · Technical Notes ·
Current Implementation · Future Evolution · Important Decisions ·
Developer Notes · Related Components · Files Involved · Dependencies ·
Things That MUST NEVER Be Changed Without Updating Documentation ·
Future Improvements`

No placeholders. No "TODO" sections. If something is genuinely undecided,
that is stated explicitly as an open question under **Future Evolution**,
not left blank.

## Current project status

**Phase 1 complete and frozen** (see `implementation-phases.md`): Django
project foundation, custom User model, Role/Permission tables, JWT
authentication, Swagger, base RBAC scaffolding. Domain apps (`projects`,
Phase 3 domain apps (`projects`, `construction`, `materials`, `facilities`,
`assets`, `maintenance`, `security`, `reports`, and `attachments`) are
implemented without REST APIs. `ai_engine`, `notifications`, and `audit`
remain deferred placeholders. Each document distinguishes current behavior
from future evolution.

**Phases 1–3 implemented:** authentication and infrastructure are verified;
the Phase 3 domain models, migrations, services, protected storage, reporting,
and domain tests are present. Domain REST APIs remain Phase 4 work.
Attachments and all other domain behavior remain unimplemented. See
`implementation-phases.md` and `known-limitations.md` for the verification gate.
