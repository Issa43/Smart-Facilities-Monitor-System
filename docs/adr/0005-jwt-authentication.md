# 0005. JWT Authentication (Access + Refresh)

## Status
Accepted

## Context
Given ADR-0001/0002 (fully separate frontend, REST API only), the
authentication mechanism needed to work for a stateless API consumed by a
cross-origin client, without requiring shared session state or
cookie-domain coupling between two independently deployed projects.

## Decision
JWT-based authentication via `djangorestframework-simplejwt`: short-lived
access tokens (default 30 min) for API calls, longer-lived refresh tokens
(default 7 days) for obtaining new access tokens, with rotation and
blacklisting enabled (a used refresh token cannot be replayed).

## Consequences
- No CSRF protection needed for the API surface (see ADR-0002) — tokens
  are sent via `Authorization` header, not cookies.
- Requires the frontend to manage token storage and refresh logic
  client-side — a coupling the frontend team must implement against
  `authentication.md`'s documented contract.
- Enables clean extension to WebSocket authentication (Phase 7) via the
  same signing key, without a separate auth mechanism for real-time
  connections (see `authentication.md` §WebSocket authentication).
- Token revocation before natural expiry requires the explicit blacklist
  mechanism (logout) — a stolen, still-valid access token cannot be
  revoked before it expires (accepted risk, mitigated by the short access
  token lifetime).

## Alternatives Considered
- **Session/cookie-based auth**: rejected — reintroduces coupling
  (shared cookie domain or CORS credential complexity) between two
  independently deployed projects, contrary to ADR-0001.
- **OAuth2/OIDC via a third-party identity provider**: rejected as
  unnecessary complexity for a single first-party frontend client; not
  precluded for a future integration scenario, just not needed now.

## Related
`authentication.md`. `security.md` §Password Policy. ADR-0001, ADR-0002.
