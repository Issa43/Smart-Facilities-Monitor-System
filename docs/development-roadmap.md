# Development Roadmap

## Purpose
The near-term, actionable execution plan — what happens next, concretely
— as distinct from `implementation-phases.md`'s full Phase 1→10
specification. This document is the "what's the next PR" view; that
document is the "what's the whole plan" view.

## Scope
Immediate and near-term sequencing (current phase + next phase in
detail). Long-range, less-certain ideas belong in `future-roadmap.md`.

## Architecture

### Immediate next step: complete Phase 2 runtime verification
The infrastructure implementation is present. On a Docker-capable host:
1. Copy `.env.example` to `.env`; replace `SECRET_KEY` and `DB_PASSWORD`.
2. Run `docker compose config --quiet` and `docker compose up -d --build`.
3. Confirm all five services are running/healthy with `docker compose ps`.
4. Run Django `check` and `makemigrations --check --dry-run` inside `backend`.
5. Run the complete pytest suite, including infrastructure PostgreSQL/Redis checks.
6. Exercise all three health endpoints and the Celery infrastructure health task.
7. Record exact results in `change-log.md`; only then mark Phase 2 complete.

Attachment implementation is not part of Phase 2 under the approved execution
scope for this phase. It remains required before Construction code that depends
on generic attachments.

### Decision needed before Phase 3 starts
The `Project.facility` ↔ `Facility.created_from_project` circular
dependency (`database-erd.md` §Reading the circular relationship) needs
an explicit call: ship `projects` and `facilities` together as a combined
Phase 3/4, or ship `projects` first with `facility` added via a later
migration once `facilities` lands. **Not yet decided** — decide at Phase
2 completion, before Phase 3 kickoff, not mid-implementation.

### Sequencing rationale (why this order, not an alternative)
- Attachments before Construction: `ProjectDocument`
  needs the attachment mechanism to exist first, not be improvised
  per-app then retrofitted.
- Security before AI (Phase 5 before 6): validates the manual workflow
  independent of AI reliability (see `implementation-phases.md`).
- Audit last among domain-adjacent phases (Phase 9): comprehensive
  coverage across all apps at once, rather than partial coverage added
  incrementally and easy to under-audit.

## Business Rules
N/A.

## Technical Notes
This document is intentionally shorter-lived in detail than
`implementation-phases.md` — its "next step" section is rewritten (not
appended to) at the start of each phase, while `implementation-phases.md`
accumulates as a permanent record.

## Current Implementation
Phase 1 complete and frozen. Phase 2 infrastructure is implemented and awaits
Docker runtime verification. No Phase 3 work has started.

## Future Evolution
Rewritten at each phase boundary — see Technical Notes.

## Important Decisions
See `implementation-phases.md` — this document doesn't introduce new
decisions, only sequences existing ones.

## Developer Notes
If you're picking up work on this project and unsure what to do next,
this document (not `implementation-phases.md`) has the concrete next
action.

## Related Components
`implementation-phases.md`, `decision-log.md`.

## Files Involved
None directly.

## Dependencies
`implementation-phases.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
N/A — this document is expected to change frequently by design.

## Future Improvements
N/A — this document's own content is the improvement tracker.
