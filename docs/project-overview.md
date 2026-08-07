# Project Overview

## Purpose
Gives any new reader (human or Claude session) a complete, non-technical
understanding of what SFLMS is, who uses it, and why it exists, before any
architectural or code-level document is read.

## Scope
The whole system's business purpose. Does not cover implementation detail
(see `system-architecture.md`) or the fine-grained business rules per
domain (see `business-domain.md`).

## Architecture
N/A at this level — see `system-architecture.md`.

## Business Rules
N/A at this level — see `business-domain.md`.

## Technical Notes

### What SFLMS is
The Smart Facility Lifecycle Management System manages a facility across
its entire life: from construction, through operational use, through
ongoing maintenance, security monitoring, and reporting — as one
continuous record rather than as disconnected tools per phase.

### Why "lifecycle" is the organizing idea
Most facility software treats construction and operations as separate
products. SFLMS deliberately models the transition: a `Project` (the
construction effort) becomes a `Facility` (the operational entity) on
completion, carrying its identity forward (`Facility.created_from_project`)
rather than starting a new, disconnected record. See ADR-0014.

### Who uses it — the four roles
- **Super Admin** — full system access, user/role management, cross-facility
  visibility. Typically IT/system owner.
- **Construction Manager** — manages assigned Projects only: phases, daily
  reports, materials, quality documentation.
- **Operations Manager** — manages assigned Facilities' Assets and
  Maintenance only.
- **Security Officer** — manages assigned Facilities' Cameras, Alerts, and
  Incidents only.

No role sees data outside what it's explicitly assigned to, except Super
Admin. See `permissions-rbac.md`.

### The five lifecycles
1. **Construction Lifecycle** — Project → Phases → Daily Reports →
   Materials → Completion → conversion to Facility.
2. **Operations Lifecycle** — Facility → Assets → health tracking.
3. **Maintenance Lifecycle** — Preventive/Corrective/Emergency Maintenance
   Orders → Execution Logs → Fault tracking.
4. **Security Lifecycle** — Cameras → AI Detection → Alerts → Incidents →
   Investigation → Closure.
5. **AI Lifecycle** — Frame capture → YOLO inference → Detection Events →
   deduplication → Alert creation → (optionally) Material consumption
   prediction, Asset health prediction.

Reporting and Notifications are cross-cutting: every lifecycle feeds them,
neither owns domain state of its own beyond its own records
(`Report`, `Notification`).

## Current Implementation
Phases 1–3 provide the access-control foundation, infrastructure, domain
models, migrations, and service-layer lifecycles. Domain REST APIs have not
been implemented yet; they remain specified in `business-domain.md` and the
architecture documents for Phase 4.

## Future Evolution
As each lifecycle is implemented, this document's high-level description
should still hold true without edits — if it doesn't, the implementation
diverged from the approved architecture and needs review before merging,
not this document needing a rewrite.

## Important Decisions
- Backend-only repository; frontend is a fully separate project (ADR-0001).
- Facility is deliberately not permanently dependent on its originating
  Project (ADR-0014) — it must be able to outlive it.

## Developer Notes
If you're implementing a feature and can't explain which of the five
lifecycles it belongs to, stop and check `business-domain.md` — it may
belong to none of them and need a scope discussion before implementation.

## Related Components
`business-domain.md`, `glossary.md`, `system-architecture.md`.

## Files Involved
None — conceptual document, no source files.

## Dependencies
`glossary.md` (terminology).

## Things That MUST NEVER Be Changed Without Updating Documentation
The four-role model. Adding a fifth role is a major architectural change
requiring updates to `permissions-rbac.md`, every ADR referencing roles,
and this document.

## Future Improvements
None currently planned at the overview level.
