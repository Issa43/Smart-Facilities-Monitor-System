# Reporting

## Purpose
Explains how PDF/Excel reports are generated without blocking the API,
and how report templates and generated files relate.

## Scope
Report generation architecture. What data goes *into* a given report type
is owned by the domain it reports on (`business-domain.md`); this
document covers the generation mechanism itself.

## Architecture

### Async generation flow
```
POST /api/v1/reports/requests/  { type, module, format, parameters, template? }
    │
    ▼
Report row created, status="queued"
    │
    ▼
Celery task: generate_report.delay(report_id)   — non-blocking, returns
    │                                               report_id immediately
    ▼
Task renders PDF (e.g., WeasyPrint/ReportLab) or Excel (e.g., openpyxl)
    │
    ▼
Report.file_path set, status="completed" (or "failed" with logged reason)
    │
    ▼
Client polls the protected report-request resource until completion
```
Reports are never generated synchronously inside a request — even a
"small" report generation is a Celery task, for consistency and because
report size is user-controlled (via `parameters`) and not safely
bounded in a request/response cycle.

### Templates
`ReportTemplate` (name, module, format, `configuration` JSON) stores
reusable column/filter layouts so a user doesn't reconfigure a report
from scratch each time. `Report.parameters` captures the *actual* filters
used for one specific generated report (a snapshot), while
`ReportTemplate.configuration` is the *reusable default* — these are
deliberately separate to let a template evolve without silently changing
the meaning of past generated reports.

## Business Rules
- A `Report` in `status="failed"` must retain the failure reason
  somewhere queryable (exact field — `parameters` extension or a new
  `error_message` field — not yet finalized, see Future Evolution) so a
  Super Admin can diagnose failures without server log access.
- Generated report files follow the same soft-delete/retention rules as
  any other `Attachment`-adjacent file — see `backup-recovery.md`.

## Technical Notes
PDF/Excel library choice is not yet finalized (WeasyPrint vs. ReportLab
for PDF; openpyxl is the practical default for Excel) — see Future
Evolution. Whichever is chosen, generation logic lives in
`apps/reports/services.py`, called from `apps/reports/tasks.py`, never
directly from `views.py` (see `coding-patterns.md` §Service Layer).

## Current Implementation
`Report` and `ReportTemplate` are implemented in `apps/reports/models.py`.
`apps/reports/services.py` validates templates and parameters, derives rows
from the owning domain models, renders PDF/XLSX files, stores them in protected
storage, and updates lifecycle state transactionally. `apps/reports/tasks.py`
provides the approved Celery boundary. The Phase 4.6 API under
`api/v1/reports/` creates queued requests, dispatches that task, and exposes
completed output only through an authorized download response. It never
serializes `Report.file_path` or a storage URL.

## Future Evolution
- Full Arabic shaping/font embedding remains deferred until an approved PDF
  dependency and font asset are selected; the dependency-free renderer is
  currently suitable for Latin text.
- Failed reports retain a bounded `_generation_error` snapshot in parameters;
  a dedicated error field remains an optional future schema refinement.
- Report expiry/cleanup policy for old generated files — see
  `backup-recovery.md`.

## Important Decisions
Async-only report generation, no synchronous path, even for small
reports (documented above) — consistent with the general async-for-heavy-work
principle (ADR-0009).

## Developer Notes
When adding a new report `module` type, add its row to this document (or
a report-types table once several exist) in the same PR.

## Related Components
`celery-tasks.md`, `business-domain.md`, `backup-recovery.md`.

## Files Involved
`apps/reports/models.py`, `apps/reports/services.py`, `apps/reports/tasks.py`.

## Dependencies
`glossary.md`, `celery-tasks.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
The async-only generation rule.

## Future Improvements
Scheduled/recurring reports (e.g., a weekly security summary auto-generated
via Celery Beat) — tracked in `future-roadmap.md`, not scheduled to a phase.
