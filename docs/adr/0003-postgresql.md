# 0003. PostgreSQL as the Database

## Status
Accepted

## Context
SFLMS's domain is deeply relational: Facility → Project → Phase → Report,
Camera → Alert → Incident, User → Role → Assignment. It also carries
compliance-adjacent data (audit logs, security incidents) where
referential integrity and transactional guarantees matter.

## Decision
PostgreSQL is the system of record for all relational data, accessed
exclusively through the Django ORM.

## Consequences
- Foreign key constraints, unique constraints, and transactions are
  enforced at the database level, not just in application code.
- JSONField usage (e.g., `Permission`-adjacent metadata, `AuditLog`
  diffs, `MaterialRequest.checklist_result`-style fields) is available
  natively via PostgreSQL's JSONB support without a separate document
  store.
- Backup/restore strategy (`backup-recovery.md`) centers on a single
  database technology, simplifying operational tooling.
- No NoSQL flexibility for genuinely document-shaped data (not currently
  needed anywhere in the domain).

## Alternatives Considered
- **MySQL/MariaDB**: comparable relational fit, but PostgreSQL's JSONB
  and stronger constraint enforcement were preferred given the JSON-field
  usage across several planned models.
- **A NoSQL store for AI detection events** (potentially high write
  volume): rejected for now — `performance.md` documents PostgreSQL
  partitioning as the mitigation if this table's volume becomes a real
  bottleneck, rather than introducing a second database technology
  speculatively.

## Related
`database-design.md`. `performance.md` §Known future bottlenecks.
