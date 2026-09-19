# 0014. Facility/Project Lifecycle Decoupling

## Status
Accepted (revises an earlier, explicitly superseded design)

## Context
An early design proposed Facility as generated *from* a completed
Project, implying a permanent one-to-one dependency (Facility exists only
in relation to the Project that created it). This was explicitly revised:
requirements clarified that (a) a Facility must be able to outlive or
operate independently of its originating Project, and (b) an *existing*
Facility must support new Projects being created against it later
(expansion/renovation work), which the original one-way-dependency design
could not represent cleanly.

## Decision
Two separate, nullable relationships:
- `Project.facility` (FK, nullable) — set at Project creation for an
  expansion Project (modifying an existing Facility), or set later via
  an explicit conversion action for a new-build Project.
- `Facility.created_from_project` (OneToOne, nullable) — records which
  Project, if any, originally created this Facility (the "genesis
  project"), for traceability only, not a dependency.

Conversion from a completed Project to a new Facility is a deliberate,
manual service-layer action (`convert_project_to_facility`), never
automatic on status change — allowing a review step before a completed
project is considered operationally live.

## Consequences
- A Facility can exist, be assigned to Operations/Security staff, and
  accrue Assets/Incidents entirely independently of whether its genesis
  Project still exists or is assigned to anyone.
- Supports the full target lifecycle (`business-domain.md` §Construction
  → Facility Conversion, §Business Domain Architecture diagram) including
  repeated future expansions of one Facility.
- Introduces the one deliberate circular reference in the schema
  (`Project.facility` ↔ `Facility.created_from_project`) — creates a
  genuine implementation-order dependency between the `projects` and
  `facilities` apps, tracked explicitly in
  `docs/reports/PHASE1_FORWARD_COMPATIBILITY_AUDIT.md` §6 and
  `implementation-phases.md` Phase 3's dependency note, rather than left
  as a surprise during implementation.

## Alternatives Considered
- **Facility permanently dependent on its Project** (the original
  design): explicitly rejected — cannot represent a Facility outliving
  or being modified independently of its originating Project.
- **A single Project-or-Facility polymorphic entity**: rejected as
  unnecessarily complex — the two are genuinely different lifecycle
  stages with different field sets and different responsible-role
  models (Construction Manager vs. Operations Manager), and conflating
  them would blur `permissions-rbac.md`'s otherwise-clean role scoping.

## Related
`business-domain.md`. `database-erd.md`. `project-workflows.md`
(Workflows 1 and 2). `decision-log.md` entry 14.
