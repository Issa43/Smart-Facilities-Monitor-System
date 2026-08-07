# Folder Structure

## Purpose
The literal, current directory tree of the repository, annotated, so any
session can locate a file without exploring the whole tree first.

## Scope
Physical file/directory layout only. Logical layering is
`backend-architecture.md`.

## Architecture

```
sflms/
├── Dockerfile                      # shared backend/worker/beat image
├── docker-compose.yml              # production-oriented service topology
├── docker-compose.override.yml     # automatic local-development overrides
├── .dockerignore
├── docker/
│   ├── entrypoint.sh               # readiness, migrations, static collection
│   └── wait_for_services.py        # PostgreSQL/Redis readiness
├── manage.py
├── requirements.txt
├── pytest.ini
├── conftest.py                     # shared pytest fixtures
├── tests/
│   └── test_infrastructure.py      # Docker/settings/health/Celery/Redis tests
├── .env.example                    # placeholders only, never real secrets
├── .gitignore
├── README.md                       # Docker-first project entry point
├── PHASE1_VERIFICATION_REPORT.md
├── PHASE1_FORWARD_COMPATIBILITY_AUDIT.md
├── REPOSITORY_AUDIT_REPORT.md
├── SFLMS_Backend_Architecture_v2.md  # pre-Phase-1 architecture spec; source of truth for unimplemented models/endpoints until each is copied into docs/ on implementation (see database-design.md §Architecture)
├── docs/                            # ← you are here — permanent engineering memory
│   ├── README.md                    # docs index
│   ├── adr/                          # formal Architecture Decision Records
│   └── *.md                          # see docs/README.md for full index
├── config/
│   ├── __init__.py                   # wires config/celery.py as the Celery app
│   ├── celery.py                     # Celery app + infrastructure health task
│   ├── urls.py                       # health + API + Swagger/Redoc routing
│   ├── wsgi.py
│   ├── asgi.py                       # Channels protocol foundation
│   └── settings/
│       ├── base.py                    # all shared settings
│       ├── development.py
│       └── production.py
└── apps/
    ├── common/                        # BaseModel, shared API tools, health — [IMPLEMENTED]
    ├── users/                         # Role, Permission, custom User            — [IMPLEMENTED]
    ├── authentication/                # JWT login/refresh/logout                — [IMPLEMENTED]
    ├── projects/                      # Project domain models/services           — [IMPLEMENTED]
    ├── construction/                  # DailyReport                              — [IMPLEMENTED]
    ├── materials/                     # Materials models/services                — [IMPLEMENTED]
    ├── facilities/                    # Minimal Facility bridge                  — [IMPLEMENTED]
    ├── assets/                        # Asset model/services                      — [IMPLEMENTED]
    ├── maintenance/                   # MaintenanceOrder and Fault               — [IMPLEMENTED]
    ├── security/                      # SecurityAlert, Incident, IncidentAction   — [IMPLEMENTED]
    ├── ai_engine/                     # AIModel, CameraDetectionEvent, tasks.py — [PLACEHOLDER, Phase 6]
    ├── notifications/                 # Notification, Channels consumers        — [PLACEHOLDER, Phase 7]
    ├── reports/                       # Report, templates, PDF/XLSX generation   — [IMPLEMENTED]
    ├── audit/                         # AuditLog, middleware/signals            — [PLACEHOLDER, Phase 9]
    └── attachments/                   # Protected Attachment system              — [IMPLEMENTED]
```

## Business Rules
N/A.

## Technical Notes
Every implemented app's internal layout matches
`backend-architecture.md` §App structure exactly. Placeholder apps
currently contain only `__init__.py` and a `README.md` stating their
target phase — this is intentional (see ADR process for why apps are
scaffolded before implementation is not itself an ADR, just a Phase 1
convention documented in `implementation-phases.md`).

## Current Implementation
Tree above reflects the repository after Phase 3 domain implementation.

## Future Evolution
This document must be updated in the same PR that adds/removes/renames a
top-level file or app directory. It is not updated for changes *within*
an existing file.

## Important Decisions
Placeholder apps are pre-created (not added fresh per phase) so
`INSTALLED_APPS` wiring and directory conventions are visible from day
one — see `PHASE1_FORWARD_COMPATIBILITY_AUDIT.md` §6.

## Developer Notes
If you can't find something, check `docs/README.md`'s document index
first, then this tree, before searching the codebase blindly.

## Related Components
`backend-architecture.md`, `implementation-phases.md`.

## Files Involved
The entire repository — this document describes all of it at the
directory level.

## Dependencies
None.

## Things That MUST NEVER Be Changed Without Updating Documentation
Any top-level directory rename or new top-level app.

## Future Improvements
Once Docker files exist, add them to the tree above in the same change.
