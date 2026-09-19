# SFLMS Repository Audit Report

**Scope:** Full repository — Phase 1 code, all 35 `docs/` documents, all
15 ADRs + index, root-level reports — audited for internal consistency,
documentation-vs-architecture contradictions, ADR accuracy, folder
structure alignment, duplicate/obsolete files, cross-reference validity,
and code/documentation synchronization, per your request before Phase 2.

**Method:** Every check below was executed programmatically against the
actual repository contents (Python scripts diffing documentation claims
against real file/code contents, grep-based reference scans, `py_compile`
re-runs) — not asserted from memory, and not taken on trust from any
partial/prior work found in the working environment. Every finding below
was independently re-verified before being reported as fixed.

**Result: 5 real issues found, all fixed. 0 remaining.**

---

## 1. Cross-Reference Validity

**Check A — markdown-syntax links** `[label](path)`: every relative link
across all 51 markdown files in `docs/` (35 root + 15 ADR + 1 ADR index),
resolved programmatically against the filesystem, relative to each
source file's own directory.
**Result: 50 links checked, 0 broken.**

**Check B — bare backtick filename references** `` `something.md` ``:
every such reference across the same 51 files, checked against the set of
all real filenames in the repository.
**Result: 1 broken reference found (Issue #4 below), now fixed — 0 remaining.**

## 2. ADR Accuracy

**Check A — every `ADR-NNNN` citation resolves to a real ADR.** Scanned
all 51 `docs/` files plus `docs/reports/SFLMS_Backend_Architecture_v2.md` for the
pattern `ADR-?\d{4}`, cross-referenced against the 15 real files in
`docs/adr/`.
**Result: every cited number (0001–0015) exists. 0 dangling references.**

**Check B — every citation's surrounding context matches that ADR's
actual topic** (not just an existing number — e.g. a citation of
"ADR-0006" should be discussing RBAC, not something unrelated). Every
citation (~85 occurrences) was extracted with its source line and
manually verified against the ADR index topic map.
**Result: 100% topically accurate. 0 mismatches.**

**Check C — `decision-log.md`'s 15 numbered entries map 1:1 to
`docs/adr/`'s 15 numbered files**, same order, same topic.
**Result: exact match, entry-for-entry.**

## 3. Folder Structure Alignment

`docs/folder-structure.md`'s documented tree was diffed against the real
repository (`find . -type f`), including: root-level files, `docs/`
count, `docs/adr/` count, every `apps/<name>/` directory's actual
contents (implemented apps' full file lists; placeholder apps' exact
`__init__.py` + `README.md` pairing), and `config/` contents.
**Result: exact match after Issue #4's fix (below) — 0 discrepancies.**

## 4. Duplicate / Obsolete Files

**Check A — duplicate basenames** across the whole repository: only
expected duplicates found (three distinct `README.md` files, at repo
root / `docs/` / `docs/adr/` — each serves a different, non-overlapping
purpose and is linked distinctly; not a defect).

**Check B — stray files not matching any documented index.** Found and
removed (Issue #5 below): 11 incorrectly-named duplicate ADR files in
`docs/adr/` that did not match the index committed in `docs/adr/README.md`.

**Result after fix: `docs/adr/` contains exactly the 15 indexed ADRs plus
the index — 0 stray or duplicate files anywhere in the repository.**

## 5. Documentation vs. Approved Architecture

Cross-checked `docs/database-design.md`, `docs/permissions-rbac.md`,
`docs/api-specification.md`, and `docs/docker.md` against
`docs/reports/SFLMS_Backend_Architecture_v2.md` (the approved pre-Phase-1 architecture
specification) for the Facility/Project lifecycle model, the four-role
permission matrix, the Attachment `entity_type`/`entity_id` decision, and
the Celery/Redis/Channels infrastructure plan.
**Result: no contradictions.** One accuracy gap found (Issue #4) — four
documents cited the architecture spec as living "at the repository root"
when it had never actually been added there.

## 6. Code ↔ Documentation Synchronization

- **Model fields**: every field in `apps/users/models.py` (`Role`,
  `Permission`, `User`) diffed against `docs/database-design.md`'s
  documented field list. **Exact match**, including `Meta.ordering` per
  model.
- **API endpoints**: `apps/users/urls.py`, `apps/authentication/urls.py`,
  and every `@action` in `apps/users/views.py` diffed against
  `docs/api-specification.md`'s endpoint table. **Exact match.**
- **Permission classes**: every class in `apps/common/permissions.py` and
  `apps/users/permissions.py` diffed against class names cited in
  `docs/permissions-rbac.md` and `docs/backend-architecture.md`.
  **Exact match.**
- **Environment variables**: every `config("VAR_NAME", ...)` call in
  `config/settings/base.py` diffed against `docs/environment.md`'s table.
  **Exact match** (the one apparent gap, `DJANGO_SETTINGS_MODULE`, is
  correctly documented but legitimately sourced via `os.environ` in
  `manage.py`/`wsgi.py`/`asgi.py`/`celery.py` rather than `base.py`'s
  `config()` calls — verified as intentional, not a gap).
- **Syntax integrity**: `python3 -m py_compile` re-run across every `.py`
  file in the repository. **0 errors.**
- **Phase 1 audit fix persistence**: `config/celery.py` and its wiring in
  `config/__init__.py` (added during the prior forward-compatibility
  audit) verified still present and correct.
- **No forbidden placeholder markers**: scanned for `TODO`/`FIXME`/`XXX`
  and bare `TBD`. The only 3 occurrences found are legitimate,
  explicitly-flagged open design questions (`celery-tasks.md`'s frame-
  capture scheduling mechanism, `backup-recovery.md`'s pg_dump-vs-WAL
  choice) or the rule statement itself in `docs/README.md` — not lazy
  placeholder content, consistent with the "no placeholders — genuinely
  undecided things are stated explicitly" policy.

---

## Issues Found and Fixed

### Issue #1 — `environment.md` stated the target value as the current default
**Problem:** `DB_HOST`/`REDIS_URL` rows implied the Docker service-name
values (`postgres`, `redis`) were already the active default, contradicting
the actual `.env.example` (`localhost`) and `known-limitations.md`.
**Fix:** Rows corrected to state the current `localhost` default
accurately, with an explicit note that it must be overridden once Docker
Compose exists (cross-referencing `known-limitations.md`).

### Issue #2 — `known-limitations.md` understated the `REDIS_URL` gap
**Problem:** Implied `REDIS_URL` already used a Docker-compatible
hostname pattern; it does not — same `localhost` gap as `DB_HOST`.
**Fix:** Corrected to list both variables as needing the same fix.

### Issue #3 — stale "Local Server" comment in `production.py`
**Problem:** `config/settings/production.py` contained a code comment
referencing "Local Server" as the deployment target — written before
Docker-first was declared official, now contradicting ADR-0004.
**Fix:** Comment rewritten to reflect Docker Compose as the official
environment, consistent with `docker.md`/ADR-0004.

### Issue #4 — architecture spec cited as "at the repository root" without existing there
**Problem:** `database-design.md`, `api-specification.md`, `docker.md`,
and `permissions-rbac.md` all cited `docs/reports/SFLMS_Backend_Architecture_v2.md` as
a repository-root file — it had only ever been delivered as a standalone
download in this conversation, never actually committed to the
repository. This made every one of those four citations factually false.
**Fix:** Copied `docs/reports/SFLMS_Backend_Architecture_v2.md` into the repository
root; `folder-structure.md` updated to list it, with a note explaining
its role (source of truth for unimplemented models/endpoints until each
is copied into `docs/` on implementation). The superseded v1 document
(`SFLMS_Database_Architecture.md`) was deliberately **not** added back —
nothing references it, and reintroducing an unreferenced, superseded
document would itself be a new inconsistency.

### Issue #5 — 11 stray duplicate ADR files
**Problem:** `docs/adr/` contained 11 files not matching the index
committed in `docs/adr/README.md` (e.g. `0001-backend-only.md` alongside
the correctly-referenced `0001-backend-only-repository.md`) — leftover
artifacts from an earlier, incompletely-finished pass at generating the
ADR set, with shorter/less-complete content than the final versions.
**Fix:** All 11 removed. `docs/adr/` now contains exactly the 15 files
referenced by every citation across the repository, no more, no less.

---

## Conclusion

Five real inconsistencies were found across ~189 files (Phase 1 code +
full documentation system) and all five are now fixed and independently
re-verified against the actual repository state — not just re-asserted.
No further contradictions, broken references, duplicate files, or
code/documentation divergence were found in any of the six audit
categories above.

**The repository is internally consistent and ready for Phase 2.**
