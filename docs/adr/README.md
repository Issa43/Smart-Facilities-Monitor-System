# Architecture Decision Records (ADR)

This directory contains formal Architecture Decision Records for SFLMS.
An ADR is the **concise, permanent statement** of a single major
technical decision — for the narrative reasoning and conversational
context behind these, see `../decision-log.md`.

## Format

Every ADR follows this fixed structure (deliberately different from the
10-section template used elsewhere in `docs/` — ADRs follow the
industry-standard ADR format instead):

```
# NNNN. Title

## Status
Accepted | Superseded by NNNN | Deprecated

## Context
What situation/problem prompted this decision.

## Decision
The decision itself, stated plainly.

## Consequences
What this makes easier, what it makes harder, what it forecloses.

## Alternatives Considered
What else was evaluated and why it was rejected.

## Related
Links to other ADRs, decision-log.md entries, or docs/ files.
```

## Rules
- ADRs are numbered sequentially and never renumbered.
- An ADR is never edited to reverse a decision — a reversed decision gets
  a **new** ADR whose Status references the one it supersedes, and the
  old ADR's Status is updated to `Superseded by NNNN`.
- Every ADR referenced elsewhere in `docs/` is a real, existing file in
  this directory — no document points to a placeholder ADR number.

## Index

| # | Title |
|---|---|
| [0001](./0001-backend-only-repository.md) | Backend-Only Repository |
| [0002](./0002-rest-api-only.md) | REST API Only, No Templates |
| [0003](./0003-postgresql.md) | PostgreSQL as the Database |
| [0004](./0004-docker-first.md) | Docker-First Environment |
| [0005](./0005-jwt-authentication.md) | JWT Authentication (Access + Refresh) |
| [0006](./0006-rbac-fixed-roles.md) | RBAC with Four Fixed Roles |
| [0007](./0007-object-level-permissions-via-assignment-tables.md) | Object-Level Permissions via Assignment Tables |
| [0008](./0008-yolo-inside-django.md) | YOLO Inference Inside Django (via Celery) |
| [0009](./0009-celery-redis-async-processing.md) | Celery + Redis for Async Processing |
| [0010](./0010-django-channels-realtime.md) | Django Channels for Real-Time Delivery |
| [0011](./0011-uuid-primary-keys.md) | UUID Primary Keys |
| [0012](./0012-soft-delete.md) | Soft Delete via `is_active` |
| [0013](./0013-attachment-entity-type-entity-id.md) | Attachments via `entity_type`/`entity_id` |
| [0014](./0014-facility-project-lifecycle-decoupling.md) | Facility/Project Lifecycle Decoupling |
| [0015](./0015-maintenance-order-work-execution-split.md) | MaintenanceOrder / WorkExecutionLog Split |
