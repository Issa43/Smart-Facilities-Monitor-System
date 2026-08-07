# Backup & Recovery

## Purpose
Defines what data must survive a failure, how it's backed up, and the
tested procedure to restore it — required before this system holds real
security incidents and audit records, not an afterthought.

## Scope
Data backup/restore strategy. Infrastructure disaster recovery (losing an
entire host) is covered only at the level of "does our backup let us
rebuild," not full DR runbook detail (out of scope until production
deployment is imminent).

## Architecture

### What must be backed up
| Data | Location | Reproducible without backup? |
|---|---|---|
| All relational data (Users, Projects, Facilities, Assets, Incidents, AuditLog...) | `postgres_data` volume | **No** — system of record |
| Uploaded files, AI snapshots, camera recordings | `media_data` volume | **No** — not derivable from the database |
| Redis (Celery queue, Channels layer, cache) | `redis_data` volume | **Yes** — queues drain/rebuild, cache repopulates; acceptable data loss on failure |

Only PostgreSQL and the media volume require a genuine backup strategy;
Redis's volume persistence is an optimization (faster restart), not a
backup requirement.

### Backup strategy (specified, not yet implemented)
```
pg_dump (or continuous WAL archiving, TBD) → offsite storage, daily
media_data volume → offsite storage, daily (rsync or equivalent)
```
Exact tooling/schedule/retention period not yet decided — see Future
Evolution. This is intentionally not guessed at with fabricated specifics
(e.g., a made-up retention number) to avoid a false sense of coverage
before a real decision is made.

### Restore procedure (specified, not yet tested)
```
1. Provision a fresh postgres container with an empty postgres_data volume
2. Restore the latest pg_dump / replay WAL into it
3. Provision a fresh media_data volume, restore the latest file backup
4. Bring up backend/celery_worker/celery_beat against the restored volumes
5. Verify: login works, a known Project/Facility/Incident record is
   present and correct, a known Attachment file opens correctly
```
**This procedure has never been executed or tested** — see Future
Evolution. A backup strategy without a tested restore is not a backup
strategy; this is flagged explicitly rather than presented as solved.

## Business Rules
`AuditLog` and `Incident` records specifically must never be lost to a
recoverable failure — they are the two tables with the clearest
compliance/legal weight (see `security.md` §Data retention). This
constrains the backup frequency decision (daily is a placeholder floor,
not a considered-sufficient answer) — see Future Evolution.

## Technical Notes
Recording retention (`CameraRecording` — how long video clips are kept
before deletion, referenced in `camera-processing.md`) is a *retention*
policy question, distinct from *backup* — retention decides what exists
at all; backup protects what's decided to exist. Both are open questions.

## Current Implementation
**Not implemented.** No backup job, offsite storage target, or tested
restore procedure exists. This is an explicit, tracked gap — see
`known-limitations.md` — not a silent omission.

## Future Evolution
Before any production deployment (not before Phase 2/Docker
introduction — this can follow shortly after, but must precede real
data):
- Choose `pg_dump` (simple) vs. WAL archiving (point-in-time recovery) —
  needs a decision based on acceptable data-loss window (RPO), not yet
  set.
- Choose offsite storage target (cloud object storage, once the
  storage-abstraction work for `media_data` exists — see
  `backend-architecture.md` §Storage) and retention period.
- **Execute and document a real test restore** — the procedure above
  must be run at least once against a non-production copy before it's
  trusted, with the result recorded in this document (pass/fail, timing).
- Define Camera recording retention period (separate from backup
  retention — see Technical Notes).

## Important Decisions
None yet — this entire area is open, deliberately not filled with
placeholder decisions. See Future Evolution for what must be decided and
when.

## Developer Notes
Do not assume backups exist. Do not build any feature that relies on
"we can always restore from backup" as a safety net until this document's
Future Evolution items are resolved and this section is updated to
reflect a tested, implemented strategy.

## Related Components
`docker.md` (volumes), `security.md` (data retention), `reporting.md`
(generated file retention).

## Files Involved
None yet — no backup tooling exists in the repository.

## Dependencies
`docker.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
Once a backup strategy is implemented, its schedule/retention/restore
procedure become subject to this rule immediately — this document must be
the first thing updated when that work lands, not a follow-up.

## Future Improvements
This entire document is itself the improvement list until a real backup
strategy is implemented and tested.
