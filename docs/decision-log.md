# Decision Log

## Purpose
A narrative, chronological account of major technical decisions and the
conversation/reasoning that produced them — the "story" complement to the
formal, structured records in `docs/adr/`. Read this for *why* and
*context*; read an ADR for the *concise, permanent statement* of a
decision.

## Scope
Cross-cutting architectural decisions made during this project's design
phase. Does not duplicate ADR content verbatim — each entry below links
to its formal ADR where one exists.

## Architecture
N/A — this is a log, not a technical specification.

## Business Rules
N/A.

## Technical Notes

### 1. Backend-only repository (ADR-0001)
Decided at project kickoff: the frontend is Pure HTML/CSS/JS, built and
maintained as a fully separate project, consuming this backend
exclusively via REST APIs. This repository never contains frontend code
or Django templates for end-user-facing pages (Django admin is the one
exception, for internal use only).

### 2. REST API only, no Django Templates, no SSR (ADR-0002)
A direct consequence of decision #1 — reinforced explicitly multiple
times across the project's planning conversations, strongly enough to be
worth its own ADR rather than treated as implied by #1.

### 3. PostgreSQL (ADR-0003)
Chosen from the outset for relational integrity across a genuinely
relational domain (Facility → Project → Phase → Report, Camera → Alert →
Incident) — no NoSQL alternative was seriously evaluated given the
strength of these relationships and the value of foreign-key/constraint
enforcement for a compliance-adjacent domain (audit logs, incidents).

### 4. Docker-first (ADR-0004)
Initially scoped as "local server, Docker-ready architecture" during
early planning (environment variables fully externalized from day one
specifically to make this transition painless). Later formalized as
Docker being the **official** environment with no supported local
execution path — a genuine scope tightening, not just a formalization of
what was already true. Phase 1 code was built and verified in a sandbox
without Docker access as a result of timing (Docker-first was declared
after Phase 1 was already complete) — this is documented as a known,
tracked gap in `known-limitations.md`, closed by Phase 2, not silently
absorbed.

### 5. JWT with access + refresh tokens (ADR-0005)
Required by decision #2 — a stateless REST API consumed by a fully
decoupled frontend cannot use session/cookie-based auth without
reintroducing coupling (shared domain for cookies, CSRF handling for a
cross-origin frontend). `djangorestframework-simplejwt` chosen for native
DRF integration and built-in token blacklisting.

### 6. Four fixed roles, RBAC not a dynamic permission engine (ADR-0006)
Requirements consistently specified exactly four roles (Super Admin,
Construction Manager, Operations Manager, Security Officer) across every
iteration of the project brief — never presented as an open or growing
set. Modeling `Role` as a lightweight reference table (not a bare code
Enum) allows it to be a real FK target and be listed via API, while
keeping the *set* of roles fixed in application logic rather than
building a fully dynamic, admin-configurable permission engine that
nothing in the requirements asked for.

### 7. Object-level permissions via Assignment tables, not django-guardian (ADR-0007)
The explicit requirement ("a project/facility can have multiple
responsible users") was satisfiable with a simple, explicit
`ProjectAssignment`/`FacilityAssignment` design — chosen over
`django-guardian` (a general-purpose object-permission framework) because
the requirement was narrow and well-defined; a general framework would
have added indirection (permission strings, generic object refs) without
the project needing that generality.

### 8. YOLO inside Django, via Celery (ADR-0008)
Explicit requirement: no microservices at this stage. The risk this
creates (blocking the request/response cycle) is addressed by Celery,
not by architectural avoidance — inference always runs in `celery_worker`,
never inline in a view. The design deliberately keeps the `ai_engine`
app's task boundary as the natural extraction point for a future service
split, without building that split prematurely.

### 9. Celery + Redis for async processing (ADR-0009)
A consequence of #8, generalized: any operation unsuitable for a
request/response cycle (report generation, predictions, notifications)
uses the same mechanism, not a separate one per feature.

### 10. Django Channels + Redis for real-time (ADR-0010)
Real-time delivery was an explicit requirement specifically for
safety-critical events (fire, smoke, intrusion, critical faults) — a
polling-only design was explicitly rejected in favor of genuine push
delivery, with polling as the fallback for offline clients (see
`notifications.md`).

### 11. UUID primary keys (ADR-0011)
Chosen specifically because Security-module URLs (Alert/Incident IDs)
should not be sequentially guessable, and because UUIDs simplify any
future multi-system integration (no cross-system ID collision risk).

### 12. Soft delete via `is_active`, not hard delete (ADR-0012)
Chosen given the project's audit-heavy nature — Incidents, Alerts, and
financial-adjacent records (Material costs) benefit from never silently
disappearing. `AuditLog` remains append-only regardless (an even stronger
guarantee than soft-delete provides).

### 13. `entity_type`/`entity_id` Attachments, not GenericForeignKey (ADR-0013)
Explicitly decided against Django's `GenericForeignKey` — simpler query
patterns, avoids a `ContentType` framework dependency for what is, in
practice, always resolved by the application already knowing which model
it's attaching to.

### 14. Facility/Project lifecycle decoupling (ADR-0014)
The most-revised decision in the project's history: initially proposed as
Facility depending permanently on its Project, then explicitly corrected
— Facility must be able to outlive and operate independently of its
originating (genesis) Project, while still supporting Project-driven
expansions of an *existing* Facility. See `database-erd.md` for the
resulting circular-reference schema.

### 15. MaintenanceOrder / WorkExecutionLog split (ADR-0015)
Initially specified as a single maintenance record with a single
`assigned_to` field; revised to separate the *request/workflow* record
from *execution* records specifically to support multiple technicians or
repeated attempts against one maintenance need without conflating "what
needs doing" with "what was done, by whom, when."

### 16. Phase 2 is infrastructure-only
The earlier implementation roadmap grouped Docker infrastructure and the
generic Attachment feature in one phase. Phase 2 was subsequently directed to
contain infrastructure only: Docker, PostgreSQL, Redis, Celery/Beat, Channels
foundation, cache, health checks, and operational configuration. Attachment
models/endpoints remain deliberately unimplemented. This changes sequencing,
not the approved attachment design in ADR-0013 or any Phase 1 architecture.

The base Compose definition is production-oriented and uses a development
override for source mounts/host ports. The application process is named
`backend` in Compose and runs ASGI via Daphne; Celery Worker and Beat reuse the
same image. These are deployment implementation choices under ADR-0004 and
ADR-0009, not new domain architecture.

## Current Implementation
Decisions #1, #2, #3, #4, #5, #6, #9 (infrastructure only), #10
(infrastructure foundation only), #11, #12, and #16 are represented in the
current codebase. Domain behavior associated with later decisions remains
deferred to its owning phase.

## Future Evolution
New entries are appended here (never edited/rewritten after the fact) as
new major decisions are made — this is a historical log, not a living
specification.

## Important Decisions
This entire document is a list of important decisions — see ADRs in
`docs/adr/` for their formal, individually-versioned counterparts.

## Developer Notes
If you're about to revisit one of these decisions, read its full
reasoning here (and its ADR) first — several (especially #14) were
already revised once with real cost; don't re-litigate without
understanding what the previous iteration got wrong.

## Related Components
`docs/adr/` (formal records), every document referenced per entry above.

## Files Involved
N/A — historical narrative, not tied to specific files.

## Dependencies
None.

## Things That MUST NEVER Be Changed Without Updating Documentation
Existing entries are never edited to reflect new information — a
decision reversal gets a *new* entry (and a new or superseding ADR)
referencing the old one, preserving the historical record.

## Future Improvements
None — this document grows by append only.
