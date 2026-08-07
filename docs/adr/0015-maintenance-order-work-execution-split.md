# 0015. MaintenanceOrder / WorkExecutionLog Split

## Status
Accepted (revises an earlier, explicitly superseded design)

## Context
An early design specified a single maintenance record with one
`assigned_to` field, conflating "what needs to happen" (the
request/workflow) with "what was actually done, by whom, when" (the
execution). This cannot represent a maintenance need requiring multiple
technicians, a failed first attempt followed by a successful second, or
any multi-session work — all realistic scenarios for facility
maintenance.

## Decision
Two separate models: `MaintenanceOrder` (asset, type, priority,
description, status, overall `assigned_to` as the primary responsible
party) represents the workflow/request; `WorkExecutionLog`
(maintenance_order FK, technician, action_taken, progress_percentage,
started_at/ended_at, notes) represents one execution session — an Order
can have many Logs.

## Consequences
- Naturally represents multi-attempt, multi-technician maintenance work
  without overloading a single record's fields or requiring awkward
  workarounds (e.g., concatenating notes from multiple sessions into one
  text field).
- `MaintenanceOrder.status` progresses independently of individual
  `WorkExecutionLog` entries — the Order's status is a rollup/summary
  state, not directly derived from the latest Log alone (exact rollup
  logic is implementation detail for `apps.maintenance.services`, not
  specified at the ADR level).
- Slightly more complex queries for "show me the current state of this
  maintenance need" (must consider both the Order and its most recent
  Log(s)) compared to a single flat record — accepted as necessary
  complexity for the workflow it represents.

## Alternatives Considered
- **Single record with `assigned_to`** (the original design): explicitly
  rejected — cannot represent multiple execution attempts/technicians.
- **`WorkExecutionLog` as a JSON array field on `MaintenanceOrder`**
  (execution history embedded rather than a separate table): rejected —
  loses relational query-ability (e.g., "show all work done by
  technician X across all orders") and per-entry FK integrity
  (`technician` as a proper FK, not a JSON-embedded reference).

## Related
`business-domain.md` §Maintenance Lifecycle. `database-erd.md`.
`project-workflows.md` (Workflow 3). `decision-log.md` entry 15.
