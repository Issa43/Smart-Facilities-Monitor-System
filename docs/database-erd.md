# Database ERD

## Purpose
A relationship-first view of the schema — how entities connect — as a
complement to `database-design.md`'s field-first view. Read this to
understand data flow between modules; read `database-design.md` for exact
field types.

## Scope
Entity relationships only, implemented and planned.

## Architecture

### Implemented (Phase 1)
```
Role (1) ──< Permission (M)
Role (1) ──< User (M)
```

### Full target ERD (planned, Phase 3+)
```
User ──< ProjectAssignment >── Project
User ──< FacilityAssignment >── Facility

Project (0..1) ──> Facility            [Project.facility, nullable]
Facility (0..1) ──> Project            [Facility.created_from_project, genesis only]

Project (1) ──< ProjectPhase (M) ──< PhaseProgressLog (M)
Project (1) ──< DailyReport (M) ──> ProjectPhase (0..1)
Project (1) ──< ProjectDocument (M)
Project (1) ──< Material (M) ──< MaterialRequest (M)
Material (1) ──< MaterialConsumptionRecord (M) ──> ProjectPhase (0..1)
Material (1) ──< MaterialPrediction (M)

Facility (1) ──< Asset (M) ──< AssetHistory (M)
Asset (1) ──< AssetHealthHistory (M)
Asset (1) ──< MaintenanceOrder (M) ──< WorkExecutionLog (M)
MaintenanceOrder (1) ──< MaintenanceChecklist (M)
Asset (1) ──< MaintenanceCalendarEvent (M) ──> MaintenanceOrder (0..1)
Asset (1) ──< Fault (M) ──< FaultTimeline (M)

Facility (1) ──< Camera (M) ──< CameraRecording (M)
Camera (1) ──< CameraDetectionEvent (M) ──> AIModel
Camera (1) ──< VehicleRecognition (M)
CameraDetectionEvent (0..1) ──> SecurityAlert (1)   [converted_to_alert]
Facility (1) ──< SecurityAlert (M)
SecurityAlert (0..1) ──> Incident (1)               [alert FK]
Incident (1) ──< IncidentAction (M)

User (1) ──< Notification (M) ──> Facility (0..1)   [broadcast notifications]
* (any BaseModel entity) ──< Attachment (M)          [entity_type + entity_id]
User (1) ──< AuditLog (M)
User (1) ──< Report (M)
ReportTemplate (1) ──< Report (M)                    [optional, via configuration]
```

### Reading the circular Project↔Facility relationship
This is the one deliberate circular reference in the schema (ADR-0014):
`Project.facility` points forward when a Project modifies an *existing*
Facility (expansion); `Facility.created_from_project` points backward to
record which Project originally created it (genesis). A Facility can have
many Projects pointing at it over time but at most one genesis Project
pointing back. See `PHASE1_FORWARD_COMPATIBILITY_AUDIT.md` §6 for the
implementation-order implication (facilities app migration must exist
before the `Project.facility` FK migration is applied, or both must ship
in the same phase using a lazy string reference).

## Business Rules
See `business-domain.md` — this document shows *shape*, not *rules*.

## Technical Notes
Every relationship above is a standard Django `ForeignKey` — no
`ManyToManyField` exists anywhere in the target schema except Django's own
`User.groups`/`user_permissions` (present but unused by SFLMS's RBAC).
Every `Attachment` relationship is `entity_type` (CharField) +
`entity_id` (UUID) — deliberately not `GenericForeignKey` (ADR-0013).

## Current Implementation
Only `Role ──< Permission`, `Role ──< User` exist today.

## Future Evolution
This diagram is updated in the same PR that adds a new FK relationship
anywhere in the codebase.

## Important Decisions
Facility/Project circular reference (ADR-0014), Attachment pattern
(ADR-0013).

## Developer Notes
When adding a new FK, add it here first as a design step, then implement
— don't reverse the order, since the ERD is where accidental circular or
overly-coupled relationships get caught before they're code.

## Related Components
`database-design.md`, `business-domain.md`.

## Files Involved
Every `apps/<domain>/models.py`.

## Dependencies
`glossary.md`, `database-design.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
Any new or removed relationship line in this diagram.

## Future Improvements
Render this as an actual generated ERD image (e.g., via
`django-extensions`' `graph_models`, already in `requirements.txt`) once
enough of the schema is implemented for it to be worth automating.
