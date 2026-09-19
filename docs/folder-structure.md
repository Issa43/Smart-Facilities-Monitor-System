# Folder Structure

## Purpose
The literal, current directory tree of the repository, annotated, so any
session can locate a file without exploring the whole tree first.

## Scope
Physical file/directory layout only. Logical layering is
`backend-architecture.md`.

## Architecture

```
Smart-Facilities-Monitor-System/
│
├── README.md                       # project entry point (models + platform)
├── LICENSE
├── .gitignore                      # Python + Node; packaging rules are root-anchored
│
│   ── Backend (Django/DRF, rooted at the repository top level) ──
├── Dockerfile                      # shared backend/worker/beat image
├── .dockerignore
├── docker-compose.yml              # production-oriented service topology
├── docker-compose.override.yml     # automatic local-development overrides
├── docker-compose.production.yml
├── docker-compose.test.yml
├── docker-compose.restore.yml      # encrypted backup/restore tooling
├── docker/
│   ├── entrypoint.sh               # readiness, migrations, static collection
│   └── wait_for_services.py        # PostgreSQL/Redis readiness
├── manage.py
├── requirements.txt
├── pytest.ini
├── conftest.py                     # shared pytest fixtures
├── .env.example                    # placeholders only, never real secrets
├── tests/
│   └── test_infrastructure.py      # Docker/settings/health/Celery/Redis tests
├── ops/                            # backup/restore and operational tooling
├── media/                          # user uploads (contents gitignored)
├── config/
│   ├── __init__.py                 # wires config/celery.py as the Celery app
│   ├── celery.py                   # Celery app + infrastructure health task
│   ├── urls.py                     # health + API + Swagger/Redoc routing
│   ├── wsgi.py
│   ├── asgi.py                     # Channels protocol foundation
│   └── settings/
│       ├── base.py                 # all shared settings
│       ├── development.py
│       ├── production.py
│       └── test.py
├── api/                            # DRF serializers, viewsets, routers (versioned)
├── apps/
│   ├── common/                     # BaseModel, shared API tools, health  — [IMPLEMENTED]
│   ├── users/                      # Role, Permission, custom User        — [IMPLEMENTED]
│   ├── authentication/             # JWT login/refresh/logout             — [IMPLEMENTED]
│   ├── projects/                   # Project domain models/services       — [IMPLEMENTED]
│   ├── construction/               # DailyReport                          — [IMPLEMENTED]
│   ├── materials/                  # Materials models/services            — [IMPLEMENTED]
│   ├── facilities/                 # Minimal Facility bridge              — [IMPLEMENTED]
│   ├── assets/                     # Asset model/services                 — [IMPLEMENTED]
│   ├── maintenance/                # MaintenanceOrder and Fault           — [IMPLEMENTED]
│   ├── safety/                     # Safety alerts domain                 — [IMPLEMENTED]
│   ├── security/                   # Security domain + consumers/routing/realtime — [IMPLEMENTED]
│   ├── ai_engine/                  # AI/CV integration surface    — [PLACEHOLDER, Phase 6]
│   ├── notifications/              # Durable Notifications + Celery tasks — [IMPLEMENTED]
│   ├── reports/                    # Report, templates, PDF/XLSX generation — [IMPLEMENTED]
│   ├── audit/                      # AuditLog, middleware/signals         — [IMPLEMENTED]
│   └── attachments/                # Protected Attachment system          — [IMPLEMENTED]
│
│   ── Frontend (React + TypeScript + Vite) ──
├── frontend/
│   ├── src/
│   │   ├── features/               # auth, construction, operations, safety,
│   │   │                           #   security, shared, super-admin
│   │   ├── components/             # shared presentational components
│   │   ├── api/                    # REST data layer against the live backend
│   │   ├── routes/                 # per-role route and navigation config
│   │   ├── lib/                    # cn, format, queryKeys, tone
│   │   ├── context/  hooks/  styles/  types/  test/
│   │   ├── App.tsx  main.tsx
│   ├── e2e/                        # Playwright specs (rbac, rehearsal)
│   ├── docs/                       # frontend-specific docs
│   └── package.json  vite.config.ts  tsconfig*.json  playwright.config.ts
│
│   ── Computer-vision models ──
├── Models/
│   ├── SmokeAndFireModel/
│   │   ├── Deployment/             # runnable fire/smoke pipeline (weights committed)
│   │   └── Results/{Train,Test}/
│   └── LicensePLatesDetectionModel(with_OCR)/
│       ├── Deployment/             # YOLO + ByteTrack + PaddleOCR pipeline
│       │                           #   .pt weights are gitignored — supply locally
│       ├── Results/{Train,Test}/
│       └── TransferLearningOnSYDataset(Yolo26n)/
│
│   ── Supporting ──
├── docs/                           # ← you are here — permanent engineering memory
│   ├── README.md                   # docs index
│   ├── adr/                        # formal Architecture Decision Records
│   ├── reports/                    # point-in-time audits and the architecture spec
│   │   ├── SFLMS_Backend_Architecture_v2.md  # pre-Phase-1 spec; source of truth for
│   │   │                                     #   unimplemented models/endpoints
│   │   ├── PHASE1_VERIFICATION_REPORT.md
│   │   ├── PHASE1_FORWARD_COMPATIBILITY_AUDIT.md
│   │   ├── REPOSITORY_AUDIT_REPORT.md
│   │   └── AI_MODEL_FITTING_REPORT.md
│   ├── verification-artifacts/     # generated QA report outputs (xlsx/pdf)
│   └── *.md                        # see docs/README.md for full index
├── screenshots/                    # dashboard screenshots used by README.md
└── mobile-fcm-test/                # standalone Android FCM push-notification probe
```

## Business Rules
N/A.

## Technical Notes
The live security Channels components are `apps/security/consumers.py`,
`apps/security/routing.py`, and `apps/security/realtime.py`. WebSocket JWT
subprotocol authentication is in `apps/authentication/websocket.py`.
`apps/notifications` owns durable recipient-specific storage and Celery jobs;
it does not own a Channels consumer.

## Current Implementation
Tree above reflects the current implemented ownership boundaries relevant to
the domain applications and realtime layer.

## Future Evolution
This document must be updated in the same PR that adds/removes/renames a
top-level file or app directory. It is not updated for changes *within*
an existing file.

## Important Decisions
Placeholder apps are pre-created (not added fresh per phase) so
`INSTALLED_APPS` wiring and directory conventions are visible from day
one — see `docs/reports/PHASE1_FORWARD_COMPATIBILITY_AUDIT.md` §6.

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
Docker files are now present and reflected above. The backend still lives at the repository root rather than under a `backend/` directory; moving it would invalidate path references in 33 of the documents under `docs/`, so it has been left in place deliberately.
