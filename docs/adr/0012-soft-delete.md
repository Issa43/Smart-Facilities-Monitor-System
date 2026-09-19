# 0012. Soft Delete via `is_active`

## Status
Accepted

## Context
SFLMS is audit-heavy by nature — Incidents, Security Alerts, Material
cost records, and general historical facility data all have value even
after a user might normally "delete" them from an active-use perspective.
Hard deletion would permanently destroy this history.

## Decision
Every `BaseModel`-descended model uses soft delete (`is_active=False`)
as its only exposed deletion mechanism. A custom manager
(`ActiveManager`, exposed as the default `objects`) filters to
`is_active=True` rows automatically; `all_objects` provides access to
soft-deleted rows when explicitly needed (e.g., an audit view).

## Consequences
- No API endpoint performs a hard `DELETE FROM` on a `BaseModel` table —
  "deleted" data remains recoverable and queryable for audit purposes.
- Requires care in query design: any raw or manually-constructed
  queryset must go through `objects` (or explicitly opt into
  `all_objects`) to respect the soft-delete filter — a manager-level
  guarantee, not something every custom query must remember unless it
  bypasses the manager.
- Unique constraints (e.g., `User.email`) apply across *all* rows
  including soft-deleted ones — a soft-deleted user's email cannot be
  reused by a new account without an explicit design decision to permit
  it (not currently built).
- `AuditLog` (Phase 9) goes further: append-only, no delete/update
  exposed at all, by any role — a stronger guarantee than soft-delete,
  reflecting its higher compliance sensitivity.

## Alternatives Considered
- **Hard delete with a separate archive table**: rejected as more
  complex than needed — soft delete via a boolean flag and manager
  filtering achieves the same recoverability with less schema
  duplication.
- **Django's `django-safedelete` or similar package**: not adopted —
  the requirement (a boolean flag + manager filter) was simple enough to
  implement directly in `apps.common.models.BaseModel` without an
  external dependency.

## Related
`database-design.md`. `security.md` §Data retention. ADR-0011.
