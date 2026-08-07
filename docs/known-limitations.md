# Known Limitations

## Purpose
An honest, current list of deliberate gaps — things that are missing not
by oversight but by explicit, documented scope decision, or that are
tracked technical debt with a known resolution point. Distinct from bugs
(which don't belong in permanent documentation) and from
`future-roadmap.md` (speculative future ideas, not current gaps).

## Scope
Current-state gaps only, each with its resolution phase/condition
referenced. This document is edited (entries removed) as gaps close —
unlike `decision-log.md`, which never edits history.

## Architecture
N/A.

## Business Rules
N/A.

## Technical Notes

### Infrastructure
- **Phase 2 runtime verification is environment-dependent.** Docker files,
  service-name defaults, health endpoints, and infrastructure tests exist, but
  completion cannot be claimed until Compose build/start/check/test commands
  pass on a Docker-capable host. Resolution: execute `docs/docker.md`'s
  verification sequence and record the result in `change-log.md`.
- **No backup/restore strategy is implemented or tested.** Resolution:
  must land before production data exists, tracked in
  `backup-recovery.md`, targeted for Phase 10 at the latest but should
  ideally land earlier once real data volume exists.

### Verification
- **Phase 1's migrations were hand-authored and verified only by static
  analysis** (syntax compilation + manual field-by-field diff against
  `models.py`), not by actually running `makemigrations --check` against
  a live Django/PostgreSQL installation — the sandbox that produced Phase
  1 had no network access to install Django. See
  `PHASE1_VERIFICATION_REPORT.md` for the full disclosure. Resolution:
  the first `docker compose exec backend python manage.py makemigrations
  --check --dry-run` run in Phase 2 closes this loop definitively.
- **No CI/CD pipeline exists.** All verification to date has been manual
  (see above). Resolution: `implementation-phases.md` Phase 10, though it
  could reasonably move earlier once Phase 2's Docker environment exists.

### Authentication
- **No password-reset-by-email flow.** `change_password` (requires
  knowing the current password) is the only self-service option; a
  forgotten password today requires Super Admin intervention. Resolution:
  requires an email backend decision, not yet scheduled to a phase — see
  `authentication.md` §Future Evolution, `future-roadmap.md`.
- **No rate limiting on `/api/auth/login/`.** Brute-force protection is
  not yet implemented. Resolution: Phase 9 (`security.md` §Future
  Evolution), should be prioritized before any production exposure.

### AI Engine
- **Detection confidence thresholds, deduplication window, and frame
  capture rate are unset** — `ai-engine.md` documents proposed starting
  values explicitly marked as unvalidated. Resolution: must be decided
  with real model performance data during Phase 6, not before (a desk
  decision here would be fabricated precision).

### Notifications
- **Per-recipient read state for facility-broadcast notifications is an
  unresolved design question** (fan-out rows vs. a read-receipt join
  table) — see `notifications.md` §Future Evolution. Resolution: Phase 7,
  must be resolved (and recorded as an ADR) before implementation, not
  during it.

### Reporting
- **PDF generation library not chosen** (WeasyPrint vs. ReportLab).
  Resolution: Phase 8, needs a quick spike against a real report layout.

### Documentation-implementation sync
- **Attachment APIs are deferred.** The Attachment model, registry, validation,
  protected storage, and access services are implemented. HTTP upload/download
  endpoints remain Phase 4 work. ADR-0013 is unchanged.

## Current Implementation
This list reflects the repository state at the time this documentation
system was created (immediately following Phase 1 completion and the
Phase 1 forward-compatibility audit).

## Future Evolution
Entries are removed (not struck through — genuinely deleted) as each gap
closes, with a corresponding entry added to `change-log.md` noting the
resolution.

## Important Decisions
Every gap listed here was a deliberate scope decision (defer to a later
phase) rather than an accidental omission — that distinction matters:
this document is not a bug tracker.

## Developer Notes
Before starting any phase, check this document for gaps that phase is
expected to close, and remove them here as part of that phase's PR — not
as a separate cleanup task.

## Related Components
`implementation-phases.md`, every document referenced per entry above.

## Files Involved
Varies per entry.

## Dependencies
`implementation-phases.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
Entries must only be removed when genuinely resolved and verified — never
removed preemptively because a phase merely "started" addressing them.

## Future Improvements
N/A — this document's entries are themselves the improvement list.
