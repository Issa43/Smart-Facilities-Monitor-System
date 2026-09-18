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
Backend uses pytest/pytest-django. The frontend uses Vitest, React Testing
Library, user-event, Jest DOM, and JSDOM. Playwright supplies isolated browser
and API E2E coverage.

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

### Runtime isolation (fail-closed)

A test run must never reach real infrastructure, whatever the shell or
container exports. This is enforced, not assumed, after a run once inherited
`DJANGO_SETTINGS_MODULE=config.settings.development` from its container and
published Celery tasks to the development Redis broker.

Two independent precedence rules caused that, and both are now closed:

1. **pytest-django** ranks the `DJANGO_SETTINGS_MODULE` environment variable
   *above* the `pytest.ini` value. `pytest.ini` therefore passes
   `--ds=config.settings.test` through `addopts`, which is the
   highest-precedence slot. An explicit `--ds` on the command line still wins,
   which is intentional.
2. **Celery** resolves `broker_url`, `broker_read_url`, `broker_write_url`, and
   `result_backend` from `os.environ` *above* Django settings, so test settings
   alone could not stop it. `conftest.py` neutralizes all four at import time,
   before Django or Celery loads.

`conftest.py` then refuses to start the session unless the settings module is
`config.settings.test`, Celery is eager, and both the Django and the Celery
broker are in-process. It also blocks every non-loopback socket, so Telegram,
USGS, GDACS, FCM, Redis, and PostgreSQL are unreachable while the Django test
client and any local helper server keep working.

`tests/test_test_isolation.py` re-executes the original incident: it runs
`tests/test_isolation_probe.py` in a subprocess with the development settings
module exported and asserts the run is still isolated, and that stripping
`addopts` aborts during configuration rather than publishing anything.

Running the suite: `pytest` from the repo root. Development and production
runtimes are untouched — they keep PostgreSQL, Redis, Celery, and Channels.

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
The 2026-08-25 full-system rehearsal gate collected 147 backend tests and all
147 passed against a freshly created PostgreSQL test database. The frontend
gate has 65 passing tests spanning API clients, adapters, forms/validation,
permissions, protected routes, loading/error states, and actual components.
Eleven Playwright workflows pass in real Chrome against the disposable
`sflms-rehearsal` Compose project: the original RBAC/object-scope checks plus
visible Super Admin, Construction, Operations, and Security lifecycle
rehearsals. `seed_e2e` refuses non-E2E databases and requires an
environment-supplied password; it never uses a real account.

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
