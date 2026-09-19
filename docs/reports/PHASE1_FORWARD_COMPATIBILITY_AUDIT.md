# SFLMS Backend — Phase 1 Forward-Compatibility Audit

> **HISTORICAL / SUPERSEDED FIELD NAMES:** This document preserves the names
> assessed during the Phase 1 planning audit. In particular,
> `Notification.user` below is superseded by the implemented required
> `Notification.recipient` field with individual `read_at` state. Current
> Notification and Batch 4 realtime contracts are defined in
> `docs/notifications.md` and ADR-0010.

Purpose: verify the Phase 1 foundation will absorb every later phase
**without breaking changes** to what's already built. One real gap was
found and fixed during this audit (§5). Everything else checks out.

---

## 1. Custom User Model — will any future model force a change?

Checked every planned FK-to-User relationship across the full architecture
(`docs/reports/SFLMS_Backend_Architecture_v2.md` §3–§9): `ProjectAssignment.user`,
`FacilityAssignment.user`, `MaintenanceOrder.assigned_to`,
`WorkExecutionLog.technician`, `Fault.reported_by`/`assigned_engineer`,
`SecurityAlert.reviewed_by`, `Incident.assigned_to`/`created_by`/`closed_by`,
`Notification.user`, `Attachment.uploaded_by`, `AuditLog.actor`,
`Report.created_by`, `AssetHealthHistory` (via `BaseModel.created_by`).

Every single one is a plain `ForeignKey(settings.AUTH_USER_MODEL)` — the
generic Django pattern that never requires touching the `User` model
itself, only adding a field on the *other* side of the relationship.
`User.id` is a UUID, matching every other model's PK type, so no type
coercion will ever be needed either.

**✅ No future model requires changing the Custom User model.**

---

## 2. BaseModel — does it cover every future model's needs?

`apps/common/models.py` provides: `id` (UUID), `created_at`, `updated_at`,
`created_by`, `is_active` (soft delete), plus `objects` (active-only) /
`all_objects` (includes soft-deleted) managers.

Cross-checked against every model field list in the architecture document:
role-specific actor fields (`approved_by`, `reviewed_by`, `assigned_to`,
`closed_by`...) are **intentionally declared per-model**, not pushed into
`BaseModel` — they're domain-specific ownership fields, not generic audit
metadata, and folding them into `BaseModel` would force every model to
carry fields it doesn't need. This matches the original design intent
(§3.1 of the DB architecture doc) and is not a gap.

**✅ BaseModel is complete for its intended scope. No breaking addition anticipated.**

---

## 3. Role & Permission — sufficient for the full RBAC design?

The approved permission matrix (architecture §6) is enforced at two layers,
neither of which touches the `Role`/`Permission` tables' schema:

1. **Coarse role check** — `HasRole(*roles)` / `IsSuperAdmin` in
   `apps/common/permissions.py`, reading `user.role.name`.
2. **Object-level filtering** — future `ProjectAssignment` /
   `FacilityAssignment` tables (Phase 3/4), consumed in each app's own
   `get_queryset()` / `permissions.py`.

`Role` (4 fixed values) and `Permission` (free-text capability strings)
are additive-only: new `Permission` rows can be seeded anytime without a
schema migration, and no future app needs a new column on `Role` itself —
it needs new *Assignment* tables, which are new apps, not changes to
`users`.

**✅ Sufficient as-is. Object-level tables are additions, not modifications.**

---

## 4. JWT — REST API / Swagger / WebSocket (Phase 7) compatibility

| Surface | Status |
|---|---|
| REST API | ✅ `DEFAULT_AUTHENTICATION_CLASSES = (JWTAuthentication,)` — every future viewset inherits this automatically, nothing to redo. |
| Swagger | ✅ `drf-spectacular` auto-detects `rest_framework_simplejwt.authentication.JWTAuthentication` and renders the Bearer "Authorize" lock icon without extra config. Added `persistAuthorization: True` this round so the token survives page reloads while developers test (quality fix, not a breaking one — see §5). **Action for you:** once the server runs locally, open `/api/docs/` and confirm the lock icon appears — that's the one part of this claim I can't execute in this sandbox. |
| WebSocket (Phase 7 / Batch 4) | ✅ Compatible by design, **additively**: `/ws/security/events/` receives the existing short-lived JWT through the WebSocket subprotocol (`sflms.jwt`, then token). Middleware validates it with Simple JWT and never accepts query-string tokens or AIKey credentials. The existing `SIGNING_KEY`/`ALGORITHM` and ASGI foundation remain unchanged. |

**✅ No breaking change required for any of the three surfaces.**

---

## 5. Settings readiness — Celery / Redis / Channels / PostgreSQL / DRF / drf-spectacular

| Component | Status before this audit | Status now |
|---|---|---|
| PostgreSQL | ✅ fully configured | unchanged |
| DRF | ✅ fully configured | unchanged |
| drf-spectacular | ✅ fully configured | + `persistAuthorization` (non-breaking addition) |
| Redis | ✅ `REDIS_URL` configured | unchanged |
| Celery | ⚠️ **settings present, but `config/celery.py` — listed in the approved architecture's own `config/` tree — was missing.** | **Fixed:** created `config/celery.py` (standard Django+Celery bootstrap, currently inert — `autodiscover_tasks()` finds nothing until Phase 6 apps add a `tasks.py`) and wired it into `config/__init__.py` per Celery's documented integration pattern. |
| Channels | ✅ `ASGI_APPLICATION` points at `config/asgi.py`; Channels, channels-redis, and Daphne are installed, with the Redis layer configured. Batch 4 replaces the empty router with the scoped security-event route. | additive routing/authentication only |

This was the **one real gap** found in this audit — now closed. It was a
missing-file gap, not a design flaw: nothing already written had to change,
a file was simply added to match the tree that was already promised in the
architecture document.

**✅ After this fix: all six components are structurally ready with zero further restructuring expected.**

---

## 6. Future apps — will any require restructuring Phase 1?

Every planned app (`projects`, `construction`, `materials`, `facilities`,
`assets`, `maintenance`, `security`, `ai_engine`, `notifications`,
`reports`, `attachments`, `audit`) already exists as an empty placeholder
with the correct internal file layout convention established, and is
pre-listed (commented) in `INSTALLED_APPS` in `config/settings/base.py`
ready to be uncommented. Adding one is: write its files, uncomment its
`INSTALLED_APPS` line, run `makemigrations`/`migrate`. Nothing in `common`,
`users`, `authentication`, or `config` needs to change for that to work.

**One non-breaking planning note, not a Phase 1 defect:** `projects.Project`
will carry a `facility` FK to `facilities.Facility`, and `facilities.Facility`
will carry `created_from_project` back to `projects.Project` — a genuine
circular dependency **between two future apps**, both scheduled to exist
by Phase 4. Recommendation for when Phase 3/4 planning starts: implement
both FKs using Django's lazy string reference (`"facilities.Facility"`) as
already planned in the architecture doc, and land the `facilities` app's
initial migration before the migration that adds `Project.facility` (or in
the same phase). This does not affect Phase 1 in any way — flagging it now
purely so it isn't a surprise later.

**✅ No future app requires touching Phase 1's structure.**

---

## Conclusion

One gap was found (`config/celery.py` missing) and has been fixed in this
same audit — a pure addition, nothing pre-existing was altered. Every other
checked item was already correct by design.

**Phase 1 foundation is frozen and future phases will build on it without
architectural modifications.**
