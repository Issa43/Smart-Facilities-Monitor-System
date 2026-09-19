# Security

## Purpose
The security posture of the system beyond authentication/authorization
mechanics — input validation, secrets handling, data retention, and
general hardening posture. Complements `authentication.md` (identity) and
`permissions-rbac.md` (access control).

## Scope
Application and infrastructure security practices. Does not repeat token
mechanics (`authentication.md`) or the permission matrix
(`permissions-rbac.md`).

## Architecture

### Secrets management
- No secret (SECRET_KEY, DB password, etc.) ever committed to the
  repository — `.env.example` contains placeholders only (enforced
  practice, see `environment.md`).
- Under Docker (official environment), secrets are injected via
  `docker-compose.yml`'s `env_file`/`environment` directives from a
  gitignored `.env`, never baked into an image layer.

### Password policy
Enforced via Django's `AUTH_PASSWORD_VALIDATORS`
(`UserAttributeSimilarityValidator`, `MinimumLengthValidator` at 8 chars,
`CommonPasswordValidator`, `NumericPasswordValidator`) at account creation
and through the same validator chain in `change_password`
(`apps/users/views.py`). No maximum length restriction,
no forced periodic rotation (rotation-forcing is a deprecated practice per
current NIST guidance and deliberately not implemented).

### Input validation
Every write path goes through a DRF serializer's `validate()` — no view
ever writes unvalidated `request.data` directly to a model. Cross-model
validation (e.g., "this Material belongs to this Project") happens in
`services.py`, called from serializer or view `validate()` methods (see
`coding-patterns.md`).

### Data retention & soft delete
Soft delete (`is_active=False`) is the default and only exposed deletion
mechanism for any `BaseModel` descendant — no API endpoint performs a
hard `DELETE FROM` on a `BaseModel` table. This matters specifically for
`AuditLog` (append-only, no delete/update exposed at all, by any role,
including Super Admin) and for Security module records (Incidents,
Alerts) where historical integrity has compliance value.

### Audit logging
`AuditLog` (Phase 9, not yet implemented) records `actor`, `action`,
`module`, `table_name`, `record_id`, `old_values`/`new_values` (JSON
diff), `ip_address`, `timestamp` for every create/update/delete/login/
permission-denied/export event. This is a distinct concern from
`BaseModel`'s own `created_by`/`created_at`/`updated_at` (those answer
"who created/touched this row last," `AuditLog` answers "show me
everything that happened, in order, across every table").

### OWASP-relevant defaults already in place
- SQL injection: Django ORM exclusively, no raw SQL in the codebase today.
- XSS: N/A at the API layer (no server-rendered HTML — REST API only,
  see ADR-0002); the frontend's responsibility to escape output.
- CSRF: N/A for JWT-authenticated API calls (no cookie-based session
  auth is used for the API); Django admin (session-based) retains CSRF
  protection by default.
- Mass assignment: DRF serializers use explicit `fields`/`read_only_fields`
  lists everywhere — never `fields = "__all__"` on a write serializer.

## Business Rules
See `permissions-rbac.md` for who can access what; this document assumes
that layer is correctly enforced and covers everything else.

## Technical Notes
`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`,
`SECURE_BROWSER_XSS_FILTER`, `SECURE_CONTENT_TYPE_NOSNIFF` are all set in
`config/settings/production.py`, not `base.py` — deliberately not active
in development to avoid HTTPS-only friction on a local Docker setup.

## Current Implementation
Password policy and JWT security properties (rotation, blacklisting) are
implemented and tested. Audit logging is not yet implemented (Phase 9).

## Future Evolution
- Rate limiting on `/api/auth/login/` (brute-force protection) — not yet
  implemented, flagged as a pre-production requirement, see
  `known-limitations.md`.
- Dependency vulnerability scanning (e.g., `pip-audit` or `safety`) as a
  CI step — not yet set up, see `implementation-phases.md` for when CI
  is introduced.

## Important Decisions
No hard delete exposed via API for `BaseModel` descendants (extension of
ADR-0012's soft-delete decision). No CSRF protection needed for the JWT
API surface (consequence of the stateless-token decision, ADR-0005).

## Developer Notes
Never add `fields = "__all__"` to a write serializer, even for an
internal-only endpoint — it silently exposes every future field added to
the model to mass assignment.

## Related Components
`authentication.md`, `permissions-rbac.md`, `environment.md`,
`backup-recovery.md`.

## Files Involved
`config/settings/production.py`, `apps/users/models.py`
(`AUTH_PASSWORD_VALIDATORS` target), `apps/audit/*` (future).

## Dependencies
`authentication.md`, `permissions-rbac.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
The soft-delete-only, no-hard-delete-via-API rule. The AuditLog
append-only rule once implemented.

## Future Improvements
Login rate limiting (`django-ratelimit` or DRF throttle classes) —
tracked for pre-production hardening, see `known-limitations.md`.
