# Database Design

## Purpose
The authoritative schema reference: every model, every field, every
relationship, every constraint — implemented or planned. This document
and the actual `models.py` files must never disagree; if they do, the
code is either wrong or this document is stale, and both are bugs.

## Scope
PostgreSQL schema design across all apps. Query-level performance tuning
is `performance.md`; the visual relationship map is `database-erd.md`.

## Architecture

### Naming conventions
- Tables: Django default (`app_modelname`, lowercase, e.g. `users_user`).
- Every model's primary key column is named `id`, type UUID.
- FK columns: `<related_model_lowercase>_id` (Django default) — e.g.
  `role_id`, `facility_id`.
- Boolean fields: `is_<adjective>` (`is_active`, `is_false_positive`) —
  never bare adjectives.
- Timestamp fields: `<verb>_at` (`created_at`, `resolved_at`,
  `acknowledged_at`) for instants; `<noun>_date` (`report_date`,
  `installation_date`) for dates without time-of-day meaning.
- Status/enum fields: always `CharField` with `choices=`, never a
  separate lookup table, unless the values need their own metadata
  (Role is the one deliberate exception — see ADR-0006).

### BaseModel (inherited by every domain model)
```python
id          = UUIDField(primary_key=True, default=uuid4)
created_at  = DateTimeField(auto_now_add=True)
updated_at  = DateTimeField(auto_now=True)
created_by  = ForeignKey(AUTH_USER_MODEL, null=True, on_delete=SET_NULL)
is_active   = BooleanField(default=True)   # soft delete
```
`User` itself does **not** inherit `BaseModel` (it predates and is
referenced BY `BaseModel.created_by`) — it defines its own `id` (UUID) and
timestamp fields directly. This is intentional, not an inconsistency: see
ADR-0011.

### Implemented schema (Phase 1)

**Role** — `id, name (unique, 4 fixed choices), description, created_at`

**Permission** — `id, role (FK→Role), permission_name`
Unique together: `(role, permission_name)`.

**User** (`AbstractBaseUser` + `PermissionsMixin`, not `BaseModel`) —
`id, full_name, email (unique, USERNAME_FIELD), phone, username (unique),
role (FK→Role, PROTECT, nullable), profile_image, status (active/inactive/
suspended), is_staff, is_superuser, created_at, updated_at` (+
`password`, `last_login` from base classes; `groups`, `user_permissions`
from `PermissionsMixin`, unused by SFLMS's own RBAC but required by
Django admin).
Indexes: `email`, `username`, `role`.

### Planned schema (Phase 3+, specified not yet migrated)
Full field lists for every planned model (Project, ProjectPhase,
Facility, Asset, MaintenanceOrder, SecurityAlert, Incident,
CameraDetectionEvent, etc.) are maintained in
`SFLMS_Backend_Architecture_v2.md` §3 at the repository root — that
document is the field-level source of truth for unimplemented models and
is intentionally not duplicated here to avoid drift between two competing
copies. **Rule: when a model from that document is implemented, its final
field list is copied into this document (§ below, per app) and from that
point *this* document becomes authoritative for it, superseding the
architecture doc.**

<!-- Per-app sections below are added here as each app is implemented. -->

## Business Rules
See `business-domain.md` for the *why* behind constraints below; this
section lists only the *what* enforced at the database level.
- `Permission`: a role cannot have the same `permission_name` twice
  (unique constraint) — prevents duplicate-permission bugs, not a
  business rule requiring app-level enforcement.
- `User.email`/`User.username`: both globally unique — login and display
  identity are never ambiguous.
- Soft delete (`is_active=False`) is the only supported deletion for any
  `BaseModel` descendant — hard deletes are never exposed via the API for
  these models (see `security.md` §Data Retention).

## Technical Notes
- UUID PKs chosen over auto-increment integers for unguessable IDs
  (important for Security module URLs) — ADR-0011.
- All FKs to `User` use `on_delete=SET_NULL` (via `BaseModel`) or
  `PROTECT` (`User.role`) — never `CASCADE` for audit-relevant
  relationships, so historical records survive user removal.
- Indexes are added deliberately per documented query pattern, not
  speculatively — each index in this document states which query it
  serves.

## Current Implementation
Users/Roles plus the Phase 3 Attachment, Project, Construction, Materials,
Facility, Asset, Maintenance, Security, and Reports schemas are implemented
and represented by app-owned migrations.

## Future Evolution
Every future migration must be preceded by an update to this document in
the same PR — not after. See `coding-standards.md` §Migration Rules.

## Important Decisions
UUID PKs (ADR-0011), soft delete (ADR-0012), `entity_type`/`entity_id`
attachments instead of GenericForeignKey (ADR-0013).

## Developer Notes
Before adding a field to any model, check whether `BaseModel` already
provides it. Before adding a new status/enum field, check
`coding-standards.md` §Model Rules for the choices-field convention.

## Related Components
`database-erd.md`, `backend-architecture.md`, `coding-standards.md`.

## Files Involved
`apps/common/models.py`, `apps/users/models.py`,
`apps/users/migrations/*`, and every future `apps/<domain>/models.py`.

## Dependencies
`glossary.md`, `business-domain.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
Any field addition, removal, or type change on any model. Any new index
or constraint.

## Future Improvements
Once 3+ domain apps are implemented, add a "query patterns → indexes"
cross-reference table so index justification stays auditable at a glance.
