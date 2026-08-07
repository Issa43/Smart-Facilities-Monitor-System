# 0006. RBAC with Four Fixed Roles

## Status
Accepted

## Context
Every iteration of the project's requirements specified exactly four
roles — Super Admin, Construction Manager, Operations Manager, Security
Officer — with clearly scoped responsibilities, never presented as an
open or extensible set.

## Decision
`Role` is modeled as a lightweight reference table (real FK target,
listable via API) but the *set of values* is fixed to four in
application logic (`Role.ROLE_CHOICES`), not dynamically
administrator-configurable. Permission enforcement is Role-name-based in
code (`HasRole`, `IsSuperAdmin` permission classes), not driven by
runtime-editable permission policy.

## Consequences
- Adding a fifth role is a deliberate architectural change (new ADR, code
  changes across every domain app's `permissions.py`), not a data-entry
  task — this is intentional friction, not an oversight.
- Keeps permission logic simple and auditable (a developer can read
  `permissions-rbac.md`'s matrix and know exactly what's enforced, rather
  than needing to inspect runtime-configured policy data).
- The `Permission` model (free-text `permission_name` per Role) exists
  today as a reference/audit table but is not consulted by any
  permission class — if a future requirement needs genuinely dynamic,
  admin-configurable permissions, that's a new architectural decision,
  not something this design silently supports already.

## Alternatives Considered
- **Fully dynamic permission engine** (Django's built-in
  `django.contrib.auth` permissions, or a custom policy table consulted
  at runtime): rejected as unnecessary complexity — nothing in the
  requirements asked for admin-configurable roles, and building for that
  speculatively would add indirection without current value.

## Related
`permissions-rbac.md`. `decision-log.md` entry 6. ADR-0007.
