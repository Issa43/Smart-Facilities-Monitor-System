# Authentication

## Purpose
The single source of truth for how identity is established and
maintained across the API and WebSocket connections.

## Scope
JWT issuance, validation, refresh, revocation. Does not cover *authorization*
(what an authenticated user may do) — see `permissions-rbac.md`.

## Architecture

### External AI machine authentication

External AI services do not use the human JWT login flow. They use the
dedicated header `Authorization: AIKey <key_id>:<secret>`. The secret is stored
only as a Django password hash and checked through Django's constant-time
password-hasher verification.

Each credential points to a roleless active User with an unusable password, so
the existing human login serializer rejects it and it receives no human RBAC
permissions. Active, unexpired, unrevoked credentials are further restricted
to explicit active Camera scopes. Facility identity is always derived from the
authorized Camera.

Machine authentication is opt-in on `POST` and `PATCH` CameraEvent operations
through the dedicated authentication, permission, camera-scope, and throttle
classes; it is not added to the global human authentication configuration.
CameraEvent `GET` operations continue to use human JWT and Security Officer
facility scope. The same AIKey credential may read current Batch 3 AI
configuration, but only for its active Camera scopes; configuration mutation
continues to require a human Super Admin JWT. Deployment must provide TLS.

### Login flow
```
POST /api/v1/auth/login/  { email, password }
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
  7 days), used only against `/api/v1/auth/refresh/`.
- **Rotation**: `ROTATE_REFRESH_TOKENS=True` — every refresh call issues a
  *new* refresh token and blacklists the old one (`BLACKLIST_AFTER_ROTATION=True`).
  A stolen, already-used refresh token cannot be replayed.
- **Logout**: `POST /api/v1/auth/logout/ { refresh }` explicitly blacklists
  that refresh token immediately, rather than waiting for it to be reused
  and rejected — this is a deliberate explicit-revocation step, not
  reliance on natural expiry.

### WebSocket authentication

Human dashboard clients offer two WebSocket subprotocol values: the literal
`sflms.jwt` followed by the existing short-lived JWT access token. The server
validates that token with Simple JWT and accepts `sflms.jwt`; it never echoes
the token. Query-string tokens and AIKey machine credentials are not accepted.

Conceptual browser handshake:

```javascript
new WebSocket("wss://example/ws/security/events/", ["sflms.jwt", accessToken])
```

Authentication is repeated on every reconnect. Token validity establishes
identity only; the consumer independently enforces the current active-user,
role, permission, and Facility-assignment rules before delivery.

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
The canonical Phase 4 route prefix is `/api/v1/auth/`; legacy Phase 1 paths
remain mounted for compatibility.

## Future Evolution
- Password-reset-by-email is explicitly **not** implemented yet (needs an
  email backend, out of Phase 1 scope) — `change_password` (requires
  knowing the old password) is the interim self-service path. See
  `known-limitations.md`.
- WebSocket JWT middleware is implemented as documented above.

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
