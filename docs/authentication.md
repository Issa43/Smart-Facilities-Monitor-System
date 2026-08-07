# Authentication

## Purpose
The single source of truth for how identity is established and
maintained across the API and (from Phase 7) WebSocket connections.

## Scope
JWT issuance, validation, refresh, revocation. Does not cover *authorization*
(what an authenticated user may do) — see `permissions-rbac.md`.

## Architecture

### Login flow
```
POST /api/auth/login/  { email, password }
    │
    ▼
SFLMSTokenObtainPairSerializer.validate()
    │  - authenticates via User.USERNAME_FIELD = "email"
    │  - rejects if user.status != "active" (suspended/inactive → 401)
    ▼
Response: { access, refresh, user: { id, full_name, email, role } }
```
The access token additionally carries custom claims (`full_name`, `role`)
so the frontend can render role-based UI without an immediate follow-up
`/me` call.

### Token lifecycle
- **Access token**: short-lived (`ACCESS_TOKEN_LIFETIME_MINUTES`, default
  30 min via `.env`), sent as `Authorization: Bearer <token>` on every
  authenticated request.
- **Refresh token**: longer-lived (`REFRESH_TOKEN_LIFETIME_DAYS`, default
  7 days), used only against `/api/auth/refresh/`.
- **Rotation**: `ROTATE_REFRESH_TOKENS=True` — every refresh call issues a
  *new* refresh token and blacklists the old one (`BLACKLIST_AFTER_ROTATION=True`).
  A stolen, already-used refresh token cannot be replayed.
- **Logout**: `POST /api/auth/logout/ { refresh }` explicitly blacklists
  that refresh token immediately, rather than waiting for it to be reused
  and rejected — this is a deliberate explicit-revocation step, not
  reliance on natural expiry.

### WebSocket authentication (Phase 7, specified not yet implemented)
Browsers cannot attach custom headers to a WebSocket handshake, so the
access token is passed as a query parameter:
`wss://.../ws/notifications/?token=<access_token>`. A custom Channels
middleware (`JWTAuthMiddleware`, to be added in
`apps/notifications/middleware.py`) will decode it using the same
`SIMPLE_JWT` `SIGNING_KEY`/`ALGORITHM` already configured, and attach the
resolved `User` to the connection `scope` before the consumer runs — no
change to token issuance itself.

## Business Rules
- A suspended (`status=suspended`) or inactive (`status=inactive`) account
  cannot obtain a new access token, even with correct credentials — the
  rejection is explicit and immediate, not just a delayed effect of
  `is_active` filtering elsewhere.
- Password requirements are enforced via Django's
  `AUTH_PASSWORD_VALIDATORS` at account creation and via `change_password`
  (minimum 8 characters, similarity/common-password/numeric checks) — see
  `security.md` §Password Policy for the full list and rationale.

## Technical Notes
- Library: `djangorestframework-simplejwt` — chosen for native DRF
  integration and built-in blacklist support (ADR-0005).
- `SIGNING_KEY = SECRET_KEY`, algorithm `HS256` (symmetric) — sufficient
  for a single-backend-service architecture; would need to move to
  asymmetric (RS256) signing only if a second service needed to *verify*
  tokens independently without holding the signing secret (not currently
  planned).
- Swagger UI documents the Bearer scheme automatically (drf-spectacular's
  built-in SimpleJWT support) with `persistAuthorization: True` so a
  developer's token survives a page reload while testing.

## Current Implementation
Fully implemented: `apps/authentication/serializers.py`,
`apps/authentication/views.py` (`LoginView`, `RefreshView`, `LogoutView`),
tested in `apps/authentication/tests/test_auth.py` (login success/failure,
suspended-account rejection, refresh, logout-blacklist-rejects-reuse).

## Future Evolution
- Password-reset-by-email is explicitly **not** implemented yet (needs an
  email backend, out of Phase 1 scope) — `change_password` (requires
  knowing the old password) is the interim self-service path. See
  `known-limitations.md`.
- WebSocket JWT middleware ships in Phase 7 — see above.

## Important Decisions
JWT with access+refresh over session-based auth — required for a fully
decoupled frontend consuming a stateless REST API (ADR-0005).

## Developer Notes
Never validate a token manually with `jwt.decode()` in application code —
always go through `rest_framework_simplejwt`'s classes so blacklist
checks and claim validation stay consistent. (The one exception is
`apps/authentication/tests/test_auth.py`, which decodes with
`verify_signature=False` purely to assert claim *contents* in a test.)

## Related Components
`permissions-rbac.md`, `security.md`, `api-specification.md`.

## Files Involved
`apps/authentication/*`, `apps/users/models.py` (`User.status`,
`USERNAME_FIELD`), `config/settings/base.py` (`SIMPLE_JWT`).

## Dependencies
`glossary.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
Token lifetimes, rotation/blacklist settings, and the suspended-account
rejection rule — all security-relevant and referenced by `security.md`.

## Future Improvements
Password-reset-by-email flow (needs `django.core.mail` backend decision —
see `future-roadmap.md`).
