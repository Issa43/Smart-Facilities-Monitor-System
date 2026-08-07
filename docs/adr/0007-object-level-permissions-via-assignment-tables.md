# 0007. Object-Level Permissions via Assignment Tables

## Status
Accepted

## Context
Role alone (ADR-0006) is too coarse: a Construction Manager must see only
their *assigned* Projects, not every Project in the system, and a
Project/Facility can have more than one responsible user. An earlier
design used a single direct FK (`construction_manager_id`,
`manager_id`) on `Project`/`Facility`, which cannot represent multiple
responsible users and was explicitly revised.

## Decision
Dedicated, explicit assignment tables — `ProjectAssignment` and
`FacilityAssignment` (user, entity, `role_type`, `assigned_at`) — are the
sole mechanism for object-level visibility. Every domain ViewSet filters
`get_queryset()` through the relevant Assignment table (except for Super
Admin, who bypasses this filtering entirely).

## Consequences
- Supports multiple responsible users per Project/Facility natively.
- Keeps the filtering logic explicit and queryable directly (`SELECT ...
  WHERE project_id IN (SELECT project_id FROM project_assignment WHERE
  user_id = ...)`), easy to reason about and index.
- Requires every new domain app with Project/Facility-scoped data to
  implement this filtering pattern in its own `permissions.py` — a
  repeated (though small) amount of per-app code, not automatically
  inherited.
- Does not generalize to non-Project/Facility object types — a new
  top-level scoping entity (if one is ever introduced) would need its own
  Assignment table, by design (deliberately not built as a generic,
  polymorphic assignment mechanism).

## Alternatives Considered
- **`django-guardian`** (general-purpose per-object permission
  framework): rejected — more general than the actual requirement (which
  is specifically "multiple responsible users per Project/Facility," not
  arbitrary per-object permission grants across arbitrary models), and
  would add a dependency and indirection (permission strings, generic
  object references) not needed here.
- **Single direct FK per entity** (`construction_manager_id`,
  `manager_id`): the original design, explicitly rejected because it
  cannot represent multiple responsible users.

## Related
`permissions-rbac.md`. `decision-log.md` entry 7. ADR-0006.
