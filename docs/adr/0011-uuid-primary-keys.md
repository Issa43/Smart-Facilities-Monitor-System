# 0011. UUID Primary Keys

## Status
Accepted

## Context
Sequential integer primary keys are guessable (`/api/incidents/1042/`
implies `/api/incidents/1041/` exists) — a meaningful concern
specifically for the Security module, where enumerable IDs could leak
information about incident volume or allow ID-guessing attempts against
`has_object_permission` backstops.

## Decision
Every `BaseModel`-descended model (and `User`, defined separately but
following the same convention) uses a UUID primary key
(`models.UUIDField(primary_key=True, default=uuid.uuid4)`), not Django's
default auto-incrementing integer.

## Consequences
- IDs are unguessable — no information leakage via sequential enumeration.
- Simplifies any future multi-system integration (no cross-system integer
  ID collision risk if data is ever merged or synced with another
  system).
- Marginally larger index size and slightly less cache-friendly
  insertion patterns than sequential integers (UUID v4 has no inherent
  ordering) — accepted tradeoff at current and anticipated scale;
  revisit only if a specific table's write volume makes this a measured
  problem (see `performance.md`).
- Requires consistent UUID handling across serializers/frontend
  (string representation in JSON) — a minor but universal convention to
  maintain.

## Alternatives Considered
- **Auto-incrementing integers with a separate public-facing slug/token**
  for security-sensitive models only: rejected as unnecessary
  complexity — applying UUIDs universally via `BaseModel` is simpler than
  maintaining two ID schemes across the codebase.
- **UUID v7 (time-ordered) instead of v4**: not used — `uuid.uuid4` is
  Python's standard library default and sufficient; v7's insertion-order
  benefits weren't judged necessary at current scale, revisit under
  `performance.md` if index fragmentation becomes measurable.

## Related
`database-design.md`. `performance.md`. ADR-0012.
