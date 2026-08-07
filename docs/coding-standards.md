# Coding Standards

## Purpose
The engineering rules every contributor (human or Claude Code) follows
when writing SFLMS backend code, so the codebase reads as one voice after
years of multiple contributors.

## Scope
Style, naming, and structural rules. Concrete implementation *patterns*
with code shape are `coding-patterns.md`; this document is the rulebook,
that document is the cookbook.

## Architecture
N/A — this is a rules document.

## Business Rules
N/A.

## Technical Notes

### Python & Django conventions
- Python 3.11+, `black`-compatible formatting (line length 100), `isort`
  for imports (stdlib → third-party → local, each group alphabetized).
- Django settings: never read `os.environ` directly in application code —
  always through `django.conf.settings`, populated from `.env` via
  `python-decouple` in `config/settings/base.py` only.
- No business logic in `settings.py` — configuration only.

### Model rules
- Every domain model inherits `apps.common.models.BaseModel` unless it has
  a documented reason not to (e.g., `User`, which predates it — see
  `database-design.md`).
- Status/enum fields: `CharField` with a `choices` tuple defined as class
  constants on the model (see `Role.ROLE_CHOICES` pattern in
  `apps/users/models.py`), never a bare Python `Enum` disconnected from
  the field, and never a separate lookup table unless the value needs its
  own metadata (Role is the deliberate exception).
- `related_name` is always set explicitly on FKs with more than one
  relationship to the same target model, and set to `"+"` (no reverse
  accessor) on purely audit-trail FKs (`BaseModel.created_by`) to avoid
  cluttering `User`'s reverse relations.
- Model `Meta.ordering` is always set explicitly — never rely on
  unordered (database-default) query results for anything user-facing.

### Serializer rules
- One serializer per *purpose*, not per model — e.g. `UserSerializer`
  (read), `UserCreateSerializer` (write, has password fields),
  `UserUpdateSerializer` (partial update, no password) — never one
  serializer trying to handle all three with conditional field logic.
- Validation that touches more than the current model's own fields (e.g.,
  "does this Material belong to the same Project as this Request") is a
  `validate()` method calling into `services.py`, never inline database
  queries scattered through serializer methods.

### View rules
- `ModelViewSet`/`ReadOnlyModelViewSet` by default; plain `APIView` only
  for genuinely non-CRUD actions (login, custom bulk actions).
- `permission_classes` set explicitly on every view/viewset — never rely
  silently on the DRF-wide default.
- `get_queryset()` is the only place object-level (Assignment-based)
  filtering happens — never in `list()`/`retrieve()` overrides.
- No business logic in views beyond: validate input (via serializer),
  call a service function or simple model method, return a response.

### Migration rules
- One logical schema change per migration file — don't bundle unrelated
  model changes into one migration for convenience.
- Data migrations (`RunPython`) always define both `forwards` and
  `reverse` functions — never a one-way data migration.
- `makemigrations --check --dry-run` must pass in CI before merge (see
  `testing.md`) — no hand-edited migration ships without this check
  passing against a real Django/PostgreSQL environment.

### Signals rules
- Django signals are used sparingly and only for cross-cutting, truly
  app-agnostic concerns (e.g., audit logging via `apps.audit`) — never as
  a substitute for an explicit `services.py` function call within a
  single request's control flow. If you can call a function directly,
  call it directly; don't reach for a signal for indirection's own sake.

### Celery rules
See `celery-tasks.md` for the full task registry and its own rules
(idempotency, retry policy, naming). Task functions themselves must not
contain business logic beyond orchestration — they call `services.py`
functions, matching the same layering as views (see
`backend-architecture.md`).

### Channels rules
Consumers (`consumers.py`) handle connection lifecycle and message
routing only — they never contain business logic. A consumer receiving
"mark as read" delegates to a `services.py` function, exactly like a view
would.

### Service Layer rules
See `coding-patterns.md` §Service Layer for the canonical shape.

### Exception handling
- Custom exceptions raised in `services.py` are caught and translated to
  DRF-appropriate responses in `views.py` (or by
  `apps.common.exceptions.custom_exception_handler` for DRF's own
  exception types) — services never construct HTTP responses themselves.
- Never use a bare `except:` — always catch the specific exception type.

### Logging
- `logging.getLogger("django")` (or a module-specific child logger) —
  never `print()` in application code.
- Log at `INFO` for expected business events worth an operational trail
  (report generated, user suspended), `WARNING` for recoverable anomalies,
  `ERROR`/`exception()` for unexpected failures needing investigation.
- Never log secrets, tokens, or passwords, even at `DEBUG` level.

### Git workflow
- `main` is always deployable. Feature branches: `feature/<short-name>`,
  fixes: `fix/<short-name>`, docs-only: `docs/<short-name>`.
- Every PR touching a model, endpoint, or architectural decision updates
  the relevant `docs/` file(s) in the same PR — see `docs/README.md`'s
  opening rule.

### Commit messages
Conventional-commit style: `<type>(<scope>): <summary>` — types: `feat`,
`fix`, `docs`, `refactor`, `test`, `chore`. Scope is the app name where
applicable (`feat(users): add change_password endpoint`).

## Current Implementation
`apps/users`, `apps/authentication`, `apps/common` follow every rule
above. Use them as the reference implementation when in doubt.

## Future Evolution
Rules are added here as new situations arise (e.g., once Celery tasks
exist, real examples replace the abstract rule text above with concrete
references).

## Important Decisions
Layered architecture (Views → Services → Models) is mandatory, not
optional per-app style (see `backend-architecture.md`).

## Developer Notes
When in doubt, match `apps/users`' existing code shape before inventing a
new pattern.

## Related Components
`coding-patterns.md`, `backend-architecture.md`, `testing.md`.

## Files Involved
All source files.

## Dependencies
`backend-architecture.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
The layering rule (no business logic in views/serializers/migrations).

## Future Improvements
Add a pre-commit hook enforcing `black`/`isort`/`makemigrations --check`
once Docker/CI is in place (see `implementation-phases.md`).
