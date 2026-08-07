# 0001. Backend-Only Repository

## Status
Accepted

## Context
SFLMS needed a Frontend (Pure HTML/CSS/JS, Enterprise Premium design
system) and a Backend (Django/DRF). The two could be developed as one
repository or two.

## Decision
This repository contains **only** the backend. The frontend is a
completely separate project, consuming this backend exclusively through
REST APIs. This repository never contains frontend build output, Django
templates for end-user pages, or frontend-specific documentation beyond
what's needed to explain API integration.

## Consequences
- Makes independent deployment/versioning of frontend and backend
  straightforward.
- Makes it easy to reason about this repository's scope: if it's not an
  API concern, it doesn't belong here.
- Requires strict API-contract discipline (`api-specification.md`) since
  there's no shared codebase to catch a frontend/backend mismatch at
  compile time.
- Forecloses server-side rendering as an option for any future feature —
  see ADR-0002.

## Alternatives Considered
- **Monorepo** (frontend + backend in one repository): rejected — the
  frontend was already built independently before backend work started,
  and the explicit requirement was a fully separate client consuming REST
  APIs.

## Related
`decision-log.md` entry 1. `docs/README.md` (repository scope statement).
ADR-0002 (direct consequence).
