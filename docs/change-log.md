# Change Log

## 2026-08-25 — Full-system rehearsal and gap closure

- Added visible real-Chrome rehearsals for all four roles, including project
  assignment persistence, material stock/request/self-approval protection,
  notifications, async PDF download, asset/work-order closure, and incident
  notes/actions/evidence/closure.
- Corrected incident response actions to start pending, fixed UUID-backed
  IncidentNote creation, and preserved long nested API paths in mutation audit
  entries without exceeding the indexed `entity_id` limit.
- Removed Construction Manager report cards that the frozen backend report
  matrix does not authorize; RBAC was preserved rather than broadened.
- Verified 147 backend tests, 65 frontend tests, 11 Playwright workflows,
  Django/migration/static/build gates, healthy Docker/Celery services, and an
  encrypted isolated backup/restore drill. Full npm audit reports zero
  vulnerabilities.
- Kept AI/CV model implementation explicitly deferred.

## 2026-08-25 — Final completion Batches 4–20

- Completed and verified four-role workflows, lifecycle enforcement, protected
  files, reports/retry, notifications, analytics, UX recovery/accessibility,
  and measured N+1/request-waterfall corrections.
- Added 144-test backend and 64-test frontend gates plus seven isolated
  Playwright E2E workflows.
- Added production frontend/Nginx image and Compose overlay, encrypted
  backup/restore with a successful isolated restore drill, JSON logs, metrics,
  and operational health thresholds.
- Resolved the npm nanoid advisory; npm audit reports zero vulnerabilities.
- Kept all AI/CV model implementation explicitly deferred.

## Purpose
A chronological record of what actually changed in the repository and
when — the ground truth of project history, complementary to
`decision-log.md` (narrative reasoning) and `docs/adr/` (formal decision
records).

## Scope
Repository-level changes: features shipped, architecture revisions,
documentation system milestones. Not a duplicate of git commit history —
this is a curated, human-readable summary at the PR/milestone level.

## Architecture
N/A.

## Business Rules
N/A.

## Technical Notes

### Entry format
```
## [YYYY-MM-DD] <Short title>
- What changed
- Why (link to ADR/decision-log entry if applicable)
- Documentation updated: <list>
```

## Current Implementation / Log

## [Phase 1] Project Foundation
- Django project skeleton (`config/`), `apps.common` (BaseModel,
  pagination, exceptions, base RBAC permission classes).
- Custom `User` model (email login field), `Role`, `Permission`.
- JWT authentication (`djangorestframework-simplejwt`): login, refresh
  (rotation + blacklist), logout.
- Swagger/OpenAPI via `drf-spectacular`.
- Full test suite: model tests, API permission tests, JWT flow tests.
- Why: establish the access-control foundation every later domain app
  builds on (ADR-0005, ADR-0006, ADR-0011, ADR-0012).
- Verification: `PHASE1_VERIFICATION_REPORT.md` (static analysis — no
  live Django/PostgreSQL available in the build sandbox, disclosed
  explicitly).

## [Phase 1 Audit] Forward-Compatibility Audit
- Found and fixed one real gap: `config/celery.py` was missing despite
  being specified in the approved architecture's `config/` tree. Added
  and wired into `config/__init__.py` (inert until Phase 6).
- Added `persistAuthorization: True` to Swagger settings (minor UX
  improvement, non-breaking).
- Confirmed: no other breaking changes anticipated for any future phase.
  Full findings: `PHASE1_FORWARD_COMPATIBILITY_AUDIT.md`.
- Conclusion recorded: "Phase 1 foundation is frozen and future phases
  will build on it without architectural modifications."

## [Documentation System] Permanent Engineering Memory Established
- Created the full `docs/` directory: 35 documents + `docs/adr/` with 15
  formal Architecture Decision Records.
- Applied the Docker-first scope tightening (Docker is now the *only*
  supported environment, not an eventual evolution from local execution
  — a genuine change from Phase 1's original local-only build, tracked
  explicitly in `known-limitations.md` rather than silently absorbed).
- Added 5 documents beyond the originally requested list, proposed and
  approved: `glossary.md`, `onboarding.md`, `celery-tasks.md`,
  `monitoring-observability.md`, `backup-recovery.md`.
- Added `docs/adr/` (formal ADR directory, alongside the narrative
  `decision-log.md`) and `coding-patterns.md`, per explicit request.
- Why: make the entire system understandable by any future Claude
  session or developer from documentation alone, per the explicit
  instruction that documentation is permanent project memory.

## [Repository Audit] Full Consistency Audit Before Phase 2
- Systematic, independently re-verified check: link integrity (51 files,
  every relative markdown-syntax link plus every bare-backtick filename
  reference), ADR number-and-topic accuracy (every `ADR-NNNN` citation
  across the repository checked against the ADR it actually names),
  `folder-structure.md` vs. the real filesystem (`find`-diffed, not
  eyeballed), model-field and endpoint-table accuracy vs. actual code
  (`apps/users/models.py`, `urls.py`, `views.py`), environment-variable
  table vs. actual `config()` calls in `config/settings/base.py`,
  duplicate/stray file scan, and a full `py_compile` re-run across every
  `.py` file.
- Found and fixed 5 real issues (all documentation/repository hygiene
  fixes, no data loss, no breaking change):
  1. `environment.md`'s `DB_HOST`/`REDIS_URL` table rows stated the
     target Docker value as if it were the current default, contradicting
     `known-limitations.md` and the actual `.env.example`/code default
     (`localhost`). Corrected to state the current default accurately.
  2. `known-limitations.md` incorrectly claimed `REDIS_URL` already used
     the Docker hostname pattern — it does not (`localhost`, same gap as
     `DB_HOST`). Corrected.
  3. `config/settings/production.py`'s code comment still said "Local
     Server" deployment target, contradicting ADR-0004 (Docker-first),
     written before that decision was finalized. Corrected.
  4. Four documents (`database-design.md`, `api-specification.md`,
     `docker.md`, `permissions-rbac.md`) cited
     `SFLMS_Backend_Architecture_v2.md` as living "at the repository
     root" — it had only ever been delivered as a standalone download,
     never actually added to the repository. Copied into the repo root;
     `folder-structure.md` updated to list it. (The superseded v1
     `SFLMS_Database_Architecture.md` was deliberately **not** added
     back — nothing references it, and reintroducing an unreferenced,
     superseded document would itself be a new inconsistency.)
  5. Eleven stray, incorrectly-named duplicate ADR files were found in
     `docs/adr/` (e.g. `0001-backend-only.md` alongside the correctly
     indexed `0001-backend-only-repository.md`), not matching the index
     committed in `docs/adr/README.md`. Removed — the correctly-named 15
     ADRs plus the index are the only files in `docs/adr/`.
- Full findings: `REPOSITORY_AUDIT_REPORT.md`.

## [2026-08-06] Phase 2 Docker & Infrastructure
- Added a shared non-root Python 3.11 image and production-oriented Compose
  stack for `backend`, PostgreSQL, Redis, Celery Worker, and Celery Beat.
- Added the development override, dependency readiness entrypoint, persistent
  volumes, health gates, restart policies, and named internal network.
- Activated Docker-aware PostgreSQL/`DATABASE_URL`, Redis cache, Celery, Redis
  Channels layer, ASGI protocol routing, environment-driven logging, WhiteNoise
  static handling, and production secret validation.
- Added `/health/`, `/health/db/`, `/health/redis/` and the side-effect-free
  `sflms.infrastructure_health` Celery task.
- Added repository-level infrastructure tests; no models, migrations, domain
  serializers/ViewSets, attachments, or other business behavior were added.
- Narrowed Phase 2 to infrastructure only by explicit instruction; the older
  combined Infrastructure + Attachments scope is superseded for sequencing,
  without changing the approved attachment architecture.
- Documentation updated: Docker, deployment, environment, testing, monitoring,
  onboarding, folder structure, known limitations, Celery registry, roadmap,
  decision log, root README, and this change log.
- Verification in the implementation workspace: focused static infrastructure
  audit and documentation-link audit passed. Docker/Python/pytest executables
  were unavailable, so Compose parsing/build/start, Django checks, migration
  drift detection, and pytest remain an explicit completion gate.

## Future Evolution
Every future PR that changes a model, endpoint, architectural decision,
or infrastructure component adds an entry here, in the same PR — this is
not a retroactively-maintained document.

## Important Decisions
This log's own existence is itself a decision: documentation is treated
as part of the codebase, versioned and updated in lockstep with code, not
as a separate, laggard artifact.

## Developer Notes
When writing a PR description, write this log's entry first — it forces
clarity on what actually changed and why before the PR is opened.

## Related Components
`decision-log.md`, `docs/adr/`, `implementation-phases.md`.

## Files Involved
N/A — meta-document.

## Dependencies
None.

## Things That MUST NEVER Be Changed Without Updating Documentation
Past entries are never edited — only appended to, matching
`decision-log.md`'s append-only convention.

## Future Improvements
None — this document's purpose is to be the improvement/change record
itself.
