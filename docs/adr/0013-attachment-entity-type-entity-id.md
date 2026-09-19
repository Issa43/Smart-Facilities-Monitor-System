# 0013. Attachments via `entity_type`/`entity_id`

## Status
Accepted

## Context
Many models across the system need file attachments (Project documents,
Daily Report photos, Asset images, Incident evidence, generated report
files). A single, generic attachment mechanism avoids duplicating a
near-identical `Attachment`-like model per domain app. Django provides
`GenericForeignKey` (via `django.contrib.contenttypes`) as a built-in
solution to exactly this problem, and was evaluated.

## Decision
`Attachment` uses a plain `entity_type` (CharField, storing the model
name as a string) + `entity_id` (UUIDField) pair — deliberately **not**
Django's `GenericForeignKey`/`ContentType` framework.

## Consequences
- Simpler queries: `Attachment.objects.filter(entity_type="project",
  entity_id=project.id)` is direct and doesn't require the
  `ContentType` lookup indirection `GenericForeignKey` involves.
- Avoids a dependency on `django.contrib.contenttypes` for this specific
  purpose (the app remains installed for Django admin/auth needs
  regardless, but `Attachment` doesn't lean on it).
- Loses `GenericForeignKey`'s referential-integrity-adjacent conveniences
  (e.g., `Prefetch`-based generic relation traversal, automatic
  reverse-generic-relation queries) — the application must construct
  `entity_type`/`entity_id` queries explicitly wherever attachments are
  fetched, which is an accepted, explicit tradeoff rather than an
  oversight.
- `entity_id` being a UUIDField (not Django's default integer) is
  consistent with ADR-0011 — every attachable model already has a UUID
  primary key, so no type-coercion complexity arises.

## Alternatives Considered
- **`GenericForeignKey`**: evaluated and explicitly rejected — the
  `ContentType` indirection was judged unnecessary overhead for a system
  where the application code fetching attachments always already knows
  which model it's dealing with (no case exists where truly
  polymorphic, type-unknown attachment traversal is needed).
- **A separate FK-based `Attachment` model per domain app** (e.g.
  `ProjectAttachment`, `IncidentAttachment`): rejected — would duplicate
  the same schema and API surface repeatedly across ~10 domain apps for
  no benefit over a single generic table.

## Related
`database-design.md`. `database-erd.md`. `backend-architecture.md`
§Storage abstraction.
