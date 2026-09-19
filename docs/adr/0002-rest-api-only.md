# 0002. REST API Only, No Templates

## Status
Accepted

## Context
Given ADR-0001 (backend-only repository, separate frontend), the backend
needed an explicit interface contract. Django supports server-side
rendering via templates, but this was explicitly and repeatedly ruled out
across the project's planning conversations.

## Decision
The backend exposes REST APIs exclusively (Django REST Framework). No
Django templates render end-user-facing pages. Django's template engine
remains configured only because the Django admin site (internal use only)
requires it.

## Consequences
- Every feature must be designed API-first — no "just render a page for
  this" shortcut is available, even for internal tooling.
- CSRF protection is unnecessary for the API surface (no cookie-based
  session auth for API consumers) — simplifies the auth story (see
  ADR-0005) but requires care that Django admin's own CSRF protection
  isn't accidentally weakened project-wide.
- API documentation (Swagger/OpenAPI via drf-spectacular) becomes the
  primary interface contract, elevating `api-specification.md` and the
  live Swagger UI to first-class importance.

## Alternatives Considered
- **Django templates for admin-style internal tooling beyond the default
  admin site**: rejected — would blur the "REST API only" boundary and
  wasn't requested.

## Related
ADR-0001. `security.md` §CSRF. `api-specification.md`.
