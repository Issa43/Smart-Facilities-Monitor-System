# Glossary

## Purpose
Defines every domain and technical term used across this documentation set
precisely, once, so that all other documents can use these terms without
re-explaining them. When a term used elsewhere in `docs/` contradicts this
glossary, the glossary wins and the other document is wrong.

## Scope
Domain vocabulary (Facility, Project, Asset...) and SFLMS-specific technical
vocabulary (Assignment table, genesis project...). Does not cover generic
Django/DRF/Celery terminology, which is assumed as prerequisite knowledge.

## Architecture
N/A — this is a reference document, not an architectural one.

## Business Rules
N/A — see `business-domain.md` for the rules governing these entities.

## Technical Notes
Terms are grouped by domain area for scanability, not alphabetically.

### Core Lifecycle Entities
- **Project** — a construction (or expansion) effort. Always has a
  lifecycle status (`Planning` → `In Progress` → `Completed` → `Operational`).
  Not every Project is currently linked to a Facility.
- **Facility** — the operational entity a Project becomes once construction
  completes. Exists independently of any single Project after creation.
- **Genesis Project** — the specific Project whose completion created a
  given Facility (`Facility.created_from_project`). A Facility has at most
  one genesis project but can receive many later Projects (expansions).
- **Expansion Project** — a Project created *with* `facility` already set,
  because it modifies an existing, already-operational Facility rather than
  building a new one.
- **Asset** — a physical, trackable component inside a Facility (HVAC unit,
  elevator, fire panel...). Has a lifecycle independent of the Facility's.
- **Work Order vs. Maintenance Order** — a `MaintenanceOrder` is the
  *request/workflow* record (what needs doing, priority, status). A
  `WorkExecutionLog` is one *execution attempt* against that order (who did
  what, when) — an order can have several execution logs (re-attempts,
  multi-technician jobs).

### Security & AI Terms
- **Detection Event** (`CameraDetectionEvent`) — a raw YOLO inference
  result above the configured confidence threshold. Logged for every
  qualifying frame, regardless of whether it becomes an alert.
- **Security Alert** — a human-facing incident candidate, created from one
  or more Detection Events after deduplication. Not every Detection Event
  produces an Alert.
- **False Positive Review** — the human confirmation step
  (`SecurityAlert.is_false_positive`, `reviewed_by`, `review_notes`) that
  closes the loop on AI accuracy without deleting the original alert.
- **Incident** — a formal security response record, optionally originating
  from a Security Alert (`Incident.alert`), but can also be raised manually.
- **Deduplication Window** — the time period during which additional
  Detection Events of the same type from the same camera are folded into
  an existing open Alert instead of creating a new one.

### Access Control Terms
- **Role** — one of exactly four fixed values: Super Admin, Construction
  Manager, Operations Manager, Security Officer. Not user-extensible.
- **Assignment Table** (`ProjectAssignment`, `FacilityAssignment`) — the
  mechanism that grants a specific user visibility into a specific
  Project/Facility. Replaces a single `manager_id` FK to allow multiple
  responsible users per entity.
- **Object-Level Permission** — access decided per-row (via Assignment
  tables), layered on top of the coarser Role check. A user can pass the
  Role check and still see zero rows if they have no Assignment.
- **RBAC** — Role-Based Access Control; the coarse layer (can this Role
  ever touch this endpoint) that Object-Level Permissions refine.

### Infrastructure Terms
- **Soft Delete** — marking `is_active=False` instead of removing a row.
  The default manager (`objects`) hides soft-deleted rows; `all_objects`
  includes them.
- **BaseModel** — the abstract model every domain model inherits from
  (UUID PK, timestamps, `created_by`, soft delete). See `database-design.md`.
- **Attachment (entity_type/entity_id pattern)** — the generic file
  attachment mechanism. Deliberately *not* Django's `GenericForeignKey` —
  see ADR-0013.

## Current Implementation
Only the Access Control and Infrastructure terms above correspond to code
that exists today (Phase 1). All Core Lifecycle and Security/AI terms
describe the target architecture for later phases.

## Future Evolution
New terms are added here the same day a new concept is introduced in code
or in an architecture document — never retroactively batched.

## Important Decisions
Terms are defined by their **first approved architectural use**, not by
common industry usage, where the two differ (e.g., "Work Order" is
deliberately distinct from "Maintenance Order" in this project, unlike
some CMMS tools that treat them as synonyms).

## Developer Notes
If you are about to introduce a new domain noun in code, check here first.
If it doesn't exist, add it here in the same PR that introduces it.

## Related Components
`business-domain.md`, `database-design.md`, `permissions-rbac.md`,
`ai-engine.md`.

## Files Involved
This is a documentation-only concept; no source files.

## Dependencies
None — this document has no upstream dependency, but is depended upon by
every other document in this directory.

## Things That MUST NEVER Be Changed Without Updating Documentation
The precise meaning of "Detection Event" vs. "Security Alert" vs.
"Incident" — these three are easy to conflate and the entire AI pipeline's
correctness depends on keeping them distinct.

## Future Improvements
None planned — this document grows by addition, not restructuring.
