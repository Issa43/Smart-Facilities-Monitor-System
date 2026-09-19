# Business Domain

## Purpose
The authoritative description of SFLMS's business rules across all five
lifecycles and how they relate. This is the document to consult before
implementing any domain app — it defines *what must be true*, independent
of how it's coded.

## Scope
All domain behavior: Construction, Operations, Maintenance, Security, AI,
Reporting, Notifications, Users/Roles/Permissions, and the relationships
between them. Does not cover database field types (`database-design.md`)
or API shapes (`api-specification.md`) — those implement these rules.

## Architecture
The five lifecycles are not five independent modules — they share entities
and hand off to each other:

```
Construction Lifecycle
   Project → Phases → Daily Reports → Materials
        │ (on completion)
        ▼
   Facility created  ──────────────┐
        │                          │
        ▼                          ▼
Operations Lifecycle          Security Lifecycle
   Assets → Health tracking      Cameras → Alerts → Incidents
        │                              ▲
        ▼                              │
Maintenance Lifecycle            AI Lifecycle
   Maintenance Orders →          Frame capture → YOLO →
   Execution Logs → Faults       Detection Events → Alerts

Reporting & Notifications: cross-cutting, consume events from all four.
```

## Business Rules

### Construction Lifecycle
- A Project starts in `Planning` and can only reach `Operational` after
  passing through `Completed`.
- Phases execute in `sequence_number` order; a Phase's `current_progress`
  rolls up into the Project's own progress percentage.
- A Phase can be rejected (`Needs Modification` / `Rejected`) and
  resubmitted — this is a normal part of the workflow, not an error state.
- Material stock is decremented via `MaterialConsumptionRecord`, never by
  directly editing `quantity_remaining` — the record is the audit trail
  the AI material-prediction feature depends on.
- A `MaterialRequest` must be `Approved` before it can be `Completed`;
  `Rejected` is terminal.
- Construction Managers create Material Requests within assigned Projects.
  Only Super Admin reviews, approves, or rejects them; Operations Managers and
  Security Officers have no decision authority in this construction workflow.
  Approval may atomically advance `Submitted -> Reviewed -> Approved` while the
  explicit `Reviewed` state remains available.

### Construction → Facility Conversion
- Conversion is a **deliberate, manual action** (`convert_project_to_facility`
  service call, Super Admin or Construction Manager), not automatic on
  status change to `Completed` — a completed project may need a review
  step before it's considered live.
- After conversion, the Facility is independent: it does not require its
  genesis Project to remain active, exist, or be assigned to anyone.
- Expansion Projects (renovating an existing Facility) skip this flow
  entirely — `facility` is set at Project creation time.

### Operations Lifecycle
- Every Asset belongs to exactly one Facility.
- `Asset.health_score` and `remaining_useful_life` are point-in-time
  snapshots; `AssetHealthHistory` is the durable trend record used for
  charts and AI predictions — the two must never be conflated.

### Maintenance Lifecycle
- A `MaintenanceOrder` represents *what needs to happen*; it does not
  itself record who did the work or when — that's `WorkExecutionLog`,
  and there can be more than one execution log per order (failed attempt,
  follow-up visit, multi-technician job).
- Preventive Maintenance is schedule-driven (`MaintenanceCalendarEvent`,
  `next_due_date`); Corrective and Emergency are event-driven (raised from
  a `Fault` or manually).
- A `Fault` has its own status lifecycle (`Reported → Investigating →
  Resolved → Closed`) independent of any `MaintenanceOrder` it spawns —
  a Fault can exist and be under investigation before any Order exists.

### Security Lifecycle
- An `Incident` does not require a `SecurityAlert` to exist (manual
  incidents are valid) but when it does originate from one, the link
  (`Incident.alert`) is preserved permanently for audit.
- `SecurityAlert.status = Converted` is set the moment an Incident is
  created from it — an Alert cannot silently belong to two Incidents.
- False positive review (`is_false_positive`, `reviewed_by`,
  `review_notes`) never deletes or hides the original Alert — it's an
  annotation, because false-positive *rate* is itself a monitored metric
  for tuning AI thresholds.

### AI Lifecycle
- Every qualifying YOLO inference is logged as a `CameraDetectionEvent`
  regardless of whether it becomes a `SecurityAlert` — this is the AI
  system's own audit trail, independent of the Security Alert audit trail.
- Deduplication (same camera + same detection type within the
  configured window) prevents alert flooding from a continuous event
  (e.g., an ongoing fire) — additional detections attach to the existing
  open Alert rather than spawning new ones.
- Material and Asset-health predictions are advisory: they create
  `MaterialPrediction` / `AssetHealthHistory` rows and (optionally) a
  `Notification` — they never automatically create a `MaterialRequest` or
  a `MaintenanceOrder`. A human always acts on the prediction.

### Cross-Cutting: Users, Roles, Permissions
- A user's visibility into Construction/Operations/Security data is never
  determined by Role alone — it's Role **and** Assignment (see
  `permissions-rbac.md`). A Construction Manager with zero
  `ProjectAssignment` rows sees zero projects, despite having the right Role.
- Suspending a user (`status = suspended`) revokes API access immediately
  (enforced at login and at every authenticated request) without deleting
  their historical `created_by`/`assigned_to` references — history must
  survive account suspension.

## Technical Notes
This document intentionally contains no Python/Django code or field
types — see `database-design.md` for the schema that implements these
rules, and `project-workflows.md` for the step-by-step operational
sequences.

## Current Implementation
Phase 3 domain models and service-layer lifecycles are implemented for
Projects, Materials, Operations, Security, and Reports. HTTP APIs remain
deferred. This document remains the specification later phases will
implement against.

## Future Evolution
As each lifecycle is implemented, any business rule discovered during
implementation that isn't captured here must be added here in the same
change, before the implementing PR is considered complete.

## Important Decisions
- Facility/Project decoupling (ADR-0014).
- MaintenanceOrder/WorkExecutionLog split (ADR-0015).
- AI predictions are advisory-only, never auto-actioned — this is a
  business rule, not a technical limitation; revisiting it requires a
  product decision, not just an engineering one.

## Developer Notes
When two lifecycles seem to need the same rule enforced in two places
(e.g., "who can close an Incident" vs. "who can close a Fault"), check
whether they're actually the same rule or coincidentally similar — do not
assume the answer without checking `permissions-rbac.md`.

## Related Components
`project-overview.md`, `permissions-rbac.md`, `database-design.md`,
`ai-engine.md`, `project-workflows.md`.

## Files Involved
None yet — awaits Phase 3+ implementation.

## Dependencies
`glossary.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
- The manual (non-automatic) Project → Facility conversion rule.
- The advisory-only nature of AI predictions.
- The MaintenanceOrder/WorkExecutionLog separation.

## Future Improvements
Consider a dedicated state-machine diagram per lifecycle once
implementation begins and real status transition edge cases are found.
