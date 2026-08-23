# Permissions & RBAC

## Purpose
The authoritative reference for who can do what: the four roles, the
object-level (Assignment-based) refinement, and exactly how both are
enforced in code.

## Scope
Authorization only (what an authenticated user may access). Authentication
(establishing identity) is `authentication.md`.

## Architecture

### Two layers, always both applied
```
Request
   │
   ▼
Layer 1 — Role check (coarse, "can this Role ever touch this endpoint")
   apps.common.permissions.HasRole / IsSuperAdmin
   apps.users.permissions.IsSuperAdminForWrite (users-specific)
   │
   ▼
Layer 2 — Object-level filtering (fine, "does this user see THIS row")
   get_queryset() filtered via ProjectAssignment / FacilityAssignment
   has_object_permission() as a defense-in-depth backstop for direct
   {id}/ access (prevents ID-guessing past the list filter)
```
A user can pass Layer 1 and still see zero rows at Layer 2 — this is
correct behavior, not a bug (e.g., a Construction Manager with no
`ProjectAssignment` rows sees an empty project list, not a 403).

### The four roles
| Role | Scope |
|---|---|
| `super_admin` | Full access to every module, every Project/Facility, user management |
| `construction_manager` | Assigned Projects only; Construction modules only |
| `operations_manager` | Assigned Facilities only; Operations/Assets/Maintenance only |
| `security_officer` | Assigned Facilities only; Security modules only |

Fixed at exactly four — adding a fifth is a breaking architectural change
(ADR-0006), not a data migration.

### Permission matrix (target — see `SFLMS_Backend_Architecture_v2.md` §6 for full detail)
| Module | Super Admin | Construction Manager | Operations Manager | Security Officer |
|---|---|---|---|---|
| Users/Roles | Full CRUD | none | none | none |
| Projects/Phases/Materials | Full | assigned only | none | none |
| Facilities | Full | read (own conversions) | assigned only | read (assigned) |
| Assets/Maintenance/Faults | Full | none | assigned only | read only |
| Cameras/Alerts/Incidents | Full | none | read only | assigned only |
| Reports | Full | Construction for assigned Projects | Assets/Maintenance for assigned Facilities | Security for assigned Facilities |
| Audit Logs | read only | none | none | none |

### Assignment tables (the object-level mechanism)
```python
ProjectAssignment:  project (FK), user (FK), role_type, assigned_at
FacilityAssignment: facility (FK), user (FK), role_type, assigned_at
```
Deliberately separate tables per entity type (not one polymorphic
assignment table) — keeps FK integrity simple and query plans direct
(ADR-0007). `role_type` allows multiple responsible users per
Project/Facility (e.g., a primary manager and a supervisor both assigned).

## Business Rules
- Super Admin bypasses object-level filtering entirely (sees everything)
  — this is checked first in every permission class, before any
  Assignment lookup, both for correctness and for query efficiency.
- A user's Role determines *which* Assignment table is even consulted —
  a Security Officer's queries never touch `ProjectAssignment`, by
  construction (their ViewSets simply don't reference it).
- Suspending a user does not delete their Assignment rows — reactivating
  a suspended account restores their prior visibility automatically.

## Technical Notes
- `apps/common/permissions.py`: `IsAuthenticatedAndActive`, `IsSuperAdmin`,
  `HasRole(*roles)` — role-layer only, reusable by every domain app.
- Domain apps add their own `permissions.py` for Layer 2, following the
  pattern established by `apps/users/permissions.py`
  (`IsSuperAdminForWrite`) once Assignment tables exist (Phase 3+).
- The `Permission` model (free-text `permission_name` per Role) exists as
  a reference/audit table today; it is **not** currently consulted by any
  permission class — enforcement is Role-name-based in code, by design
  (see ADR-0006 rationale). If a future requirement needs dynamic,
  admin-configurable permissions, that's a deliberate architecture change,
  not an oversight — document it as a new ADR before implementing.

## Current Implementation
Layer 1 (`HasRole`, `IsSuperAdmin`, `IsSuperAdminForWrite`) is implemented.
Layer 2 is implemented through `ProjectAssignment` for Construction Manager
APIs and `FacilityAssignment` for Operations Manager and Security Officer
APIs. These API groups filter querysets by active assignments, with the Super
Admin bypass applied first.

The Phase 4.6 Reports API applies the same two layers. Template visibility is
module-scoped; only Super Admin may create or update templates. Non-admin
report requests must include an actively assigned `project_id` or
`facility_id` appropriate to the role and are visible only to their creator.
Super Admin retains the global module, request, and download bypass.

## Future Evolution
`ProjectAssignment`/`FacilityAssignment` land in Phase 3/4 alongside
`projects`/`facilities`. Every domain app's `permissions.py` from that
point on must filter `get_queryset()` via the relevant Assignment table —
this is not optional per-app discretion.

## Important Decisions
RBAC as fixed 4-role enum, not a dynamic permission engine (ADR-0006).
Object-level permissions via Assignment tables, not `django-guardian`
(ADR-0007) — simpler, more explicit, and matches the exact "multiple
responsible users per entity" requirement without a general-purpose
object-permission framework's overhead.

## Developer Notes
When writing a new ViewSet's `get_queryset()`, always check Super Admin
first, then branch by `request.user.role.name`, then filter by the
relevant Assignment table for that role — never write a query that
implicitly returns everything and relies solely on `has_object_permission()`
to hide rows (that leaks row *existence* via 403-vs-404 timing/behavior
differences and defeats the list-level filtering guarantee).

## Related Components
`authentication.md`, `business-domain.md`, `api-specification.md`.

## Files Involved
`apps/common/permissions.py`, `apps/users/permissions.py`, every future
`apps/<domain>/permissions.py`.

## Dependencies
`glossary.md`, `authentication.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
The four-role list. The rule that Super Admin always bypasses object-level
filtering. The permission matrix table above.

## Future Improvements
Once 3+ domain apps implement Layer 2, extract the common
"Super Admin bypass, else filter by Assignment" logic into a reusable
`apps.common` base permission/queryset mixin to remove per-app duplication.
