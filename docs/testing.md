# Testing

## Purpose
The test strategy: what layers are tested, how, and what "done" means for
test coverage on a new feature.

## Scope
Test methodology and conventions. Individual test *files* are documented
implicitly by existing (they're self-describing); this document covers
the strategy that governs them.

## Architecture

### Test stack
`pytest` + `pytest-django` (not Django's built-in `TestCase` runner —
chosen for fixture composability and less boilerplate), `factory-boy`
available for future complex object graphs (not yet needed at Phase 1's
simplicity — `conftest.py` fixtures suffice so far).

### Test layout (per app)
```
apps/<name>/tests/
├── test_models.py     — model-level: field constraints, custom methods,
│                          manager behavior (e.g., soft-delete filtering)
├── test_api.py         — endpoint-level: permission enforcement, request/
│                          response shape, status codes, pagination
└── test_services.py    — once services.py exists: business logic in
                            isolation from HTTP, including Celery task
                            bodies called as plain functions
```

### What "tested" means for a new feature
A new endpoint is not done until its tests cover:
1. **Happy path** — valid request → expected response/state change.
2. **Permission enforcement** — at least one role that should be denied,
   asserted as denied (403/401, not just "didn't crash").
3. **Object-level filtering** (once Assignment tables exist) — a user
   assigned to object A does not see object B in a list response.
4. **Validation failure** — at least one invalid-input case → 400 with a
   useful error body, not just any 4xx.

### Fixtures (`conftest.py`, project root)
Shared fixtures: `api_client`, one fixture per role
(`role_super_admin`, `role_construction_manager`, ...), one authenticated
user per role, `authenticated_client` (Super Admin, the common case).
New domain-specific fixtures (a sample `Project`, `Facility`...) are added
to `conftest.py` once those apps exist, following the same naming
convention (`<role>_user`, `sample_<model_lowercase>`).

### Integration tests
Multi-step workflows (`project-workflows.md`) get their own integration
test exercising the full sequence end-to-end — e.g., a
`test_construction_to_facility_workflow.py` that creates a Project,
completes it, converts it, and asserts the resulting Facility state — not
just unit tests of each step in isolation.

### Infrastructure tests (`tests/test_infrastructure.py`)
Phase 2 adds repository-level tests outside any domain app. They verify:
- Docker-aware PostgreSQL, Redis cache, Celery, and Channels settings.
- Liveness and dependency health endpoints, including HTTP 503 behavior.
- A real PostgreSQL `SELECT 1` and Redis cache round-trip in Compose.
- Celery broker/result configuration and the side-effect-free health task.
- Required Compose services, volumes, health gates, restart policy, network,
  and development-only host port exposure.

These are infrastructure tests, not application/domain tests. They require the
Compose PostgreSQL and Redis services to be healthy.

## Business Rules
N/A.

## Technical Notes
- `pytest.ini`: `DJANGO_SETTINGS_MODULE = config.settings.development`,
  `--reuse-db` for faster local iteration (drop `--create-db` once to
  force a fresh schema after a migration change).
- Test database is a separate PostgreSQL database created automatically
  by `pytest-django` — requires `CREATEDB` privilege on the configured
  `DB_USER` (see `environment.md`).
- Under Docker (official environment — ADR-0004), tests run via
  `docker compose exec backend pytest`, never against a host-installed Python
  environment — see `docker.md` §Developer Notes.

## Current Implementation
`apps/users/tests/` (`test_models.py`, `test_api.py`) and
`apps/authentication/tests/test_auth.py` fully implement this strategy for
Phase 1's scope: model constraints, JWT login/refresh/logout including
suspended-account rejection and blacklist-prevents-reuse, permission
enforcement (non-Super-Admin denied on user management endpoints).
`tests/test_infrastructure.py` implements Phase 2 infrastructure coverage.

## Future Evolution
Every domain app adds `test_models.py`/`test_api.py` (and
`test_services.py` once it has one) matching this layout at
implementation time — not as a follow-up task.

## Important Decisions
`pytest`/`pytest-django` over Django's built-in test runner — better
fixture reuse across a growing number of apps sharing the same role/user
setup.

## Developer Notes
Run `pytest -v --reuse-db` for fast local iteration;
`python manage.py makemigrations --check --dry-run` before every commit
touching a model (see `coding-standards.md` §Migration Rules).

## Related Components
`coding-standards.md`, `coding-patterns.md`, `docker.md`.

## Files Involved
`pytest.ini`, `conftest.py`, `tests/test_infrastructure.py`, every
`apps/<name>/tests/*`.

## Dependencies
`coding-standards.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
The four-point "what tested means" checklist above — it's the bar every
new endpoint is held to.

## Future Improvements
Add coverage reporting (`pytest-cov`) with a minimum-threshold CI gate
once Docker/CI exists (`implementation-phases.md`).
