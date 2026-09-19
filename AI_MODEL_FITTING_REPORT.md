# AI Model ↔ Backend/Database Fitting Report

**Status:** Analysis only — **no code, schema, or migration was changed.**
**Date:** 2026-09-18
**Scope:** Verification that the external AI models' outputs fit the SFLMS backend contracts and PostgreSQL schema, with focus on (a) ANPR plate-number and vehicle-type storage and (b) the Intrusion time-restriction mechanism.

---

## 1. How this was verified

- **Schema inspection** — Django model field definitions, DB constraints, and indexes in `apps/security/models.py`.
- **In-memory contract testing** — `CameraEventCreateSerializer` run against ~60 realistic model-output payloads. No database writes, no probe data created.
- **Prior live evidence** — 59/59 HTTP probes against the running API earlier in this workstream.

Every claim below is backed by a measured result. Nothing is inferred from documentation alone.

**Severity legend**

| Level | Meaning |
|---|---|
| 🔴 **BLOCKER** | Will cause wrong data, silent corruption, or false/missed alerts in production |
| 🟠 **HIGH** | Will cause event rejection or operational failure unless the AI side adapts |
| 🟡 **MEDIUM** | Data-quality or forensic gap; system still functions |
| 🔵 **INFO** | Constraint the AI team must know; backend change not necessarily required |

---

## 2. ANPR — License plate number storage

### 2.1 🔴 BLOCKER — Plate normalization is too weak for OCR output

**Current implementation** (`apps/security/models.py`, `AuthorizedVehicle.normalize_plate`):

```python
@staticmethod
def normalize_plate(value):
    return (value or "").strip().upper()
```

It only trims outer whitespace and uppercases. It does **not** remove internal separators or unify digit forms.

**Measured result** — the same physical plate produced **7 distinct stored values**:

| Raw OCR output | Stored value |
|---|---|
| `ABC-1234` / `abc-1234` / `" ABC-1234 "` | `ABC-1234` |
| `ABC 1234` / `abc 1234` | `ABC 1234` |
| `ABC1234` | `ABC1234` |
| `ABC--1234` | `ABC--1234` |
| `ABC.1234` | `ABC.1234` |
| `ABC_1234` | `ABC_1234` |
| `أ ب ج ١٢٣٤` | `أ ب ج ١٢٣٤` |

**Why this is a blocker.** `currently_authorized_vehicle()` does an **exact match** on the normalized plate:

```python
AuthorizedVehicle.objects.filter(plate_number=normalized)
```

And the server **overrides** the AI's `authorized` claim. So if the registry holds `ABC-1234` and the OCR emits `ABC 1234`:

1. The registry lookup misses → server computes `authorized = False`.
2. If the AI sent `authorized: true` (it read the registry and matched loosely), the request is **rejected `400`**.
3. If the AI sent `authorized: false`, the event is stored as unauthorized and a **`high`-severity SecurityAlert plus FCM push is raised for an authorized vehicle** — a false alarm on every pass through the gate.

Because `AuthorizedVehicle.plate_number` is `unique=True`, operators can also unknowingly register `ABC-1234` and `ABC 1234` as two separate vehicles.

**Required change**

- Strengthen `normalize_plate()` to a canonical form: strip **all** non-alphanumeric characters (spaces, dashes, dots, underscores), uppercase, and normalize Arabic-Indic digits (`٠١٢٣٤٥٦٧٨٩`) to ASCII `0-9`. Consider Unicode NFKC normalization for Arabic letter forms.
- Apply the identical function on **both** the registry write path and the event ingest path (it already is shared — keep it that way).
- **A data migration is required** to re-normalize existing `AuthorizedVehicle.plate_number` rows, with a duplicate-collision check before applying the new `unique` constraint.
- Agree with the AI team on the exact canonical form for **Saudi dual-script plates** (Arabic + Latin). This is a decision, not a default — it must be written into the external contract document.

---

### 2.2 🟡 MEDIUM — Raw OCR text is discarded

**Measured:** submitted `"  abc 1234  "` → stored `'ABC 1234'`. The serializer overwrites the field with the normalized value, and `CameraEvent` has **no** `plate_number_raw` / `ocr_text` field.

The exact characters the OCR actually read are lost. That removes the ability to audit a disputed match, tune the OCR against ground truth, or investigate a false alarm after the fact.

**Required change:** add a nullable `plate_number_raw` (`CharField(max_length=64, null=True)`) to `CameraEvent`, populated from the submitted value before normalization. Store normalized in `plate_number` for matching, raw for forensics. **Requires a migration.**

---

### 2.3 🟡 MEDIUM — No provenance link from the event to the registry entry

**Measured:** `CameraEvent` relations are `camera`, `created_by`, `ingestion_credential`, `roi`, `security_alert`. There is **no FK to `AuthorizedVehicle`**.

The authorization decision survives only as a bare boolean. You cannot tell *which* registry entry authorized a vehicle, and if that entry is later edited, expired, or deactivated, the historical basis for the decision is unrecoverable.

**Required change:** add nullable `authorized_vehicle = FK(AuthorizedVehicle, null=True, on_delete=PROTECT)` set at creation time when the lookup matches. **Requires a migration.**

---

### 2.4 🔵 INFO — Plate field capacity is adequate

`plate_number` is `max_length=32` on **both** `CameraEvent` and `AuthorizedVehicle` — consistent, no truncation mismatch. Verified: 32 chars accepted, 33 rejected cleanly with a field error. Lowercase input is uppercased on ingest as intended.

No change required.

---

## 3. ANPR — Vehicle type

### 3.1 🟠 HIGH — Enum does not match common detector label sets

**Backend choices:** `car`, `truck`, `van`, `bus`, `motorcycle` (`max_length=20`).

**Measured acceptance:**

| Label | Result |
|---|---|
| `car`, `truck`, `van`, `bus`, `motorcycle` | ✅ ACCEPT |
| `motorbike` | ❌ REJECT |
| `bicycle` | ❌ REJECT |
| `pickup`, `suv`, `trailer` | ❌ REJECT |
| `Car`, `CAR` | ❌ REJECT (case-sensitive) |
| `train`, `person` | ❌ REJECT |

Two concrete mismatches against a COCO-trained detector (the most likely starting point):

- COCO emits **`motorbike`** (in several popular weight sets) — the backend only accepts `motorcycle`.
- COCO has **no `van` class**; vans surface as `car` or `truck`.
- COCO **does** emit `bicycle` and `train`, which have nowhere to go.
- Matching is **case-sensitive** — `Car` is rejected.

**Required change — pick one:**

- **(a) Preferred, no migration:** the AI side owns a documented label-mapping table (`motorbike→motorcycle`, `pickup/suv→car`, etc.) and normalizes case before POST. Backend unchanged. This keeps the controlled vocabulary intact.
- **(b) Backend change:** extend `VehicleType` choices and/or accept case-insensitively. **Requires a migration** and widens the vocabulary the UI must render.

Whichever is chosen must be written into the external AI contract. Today it is undefined, and a rejected event is a **lost vehicle record** because the AI has no retry-with-correction path.

---

### 3.2 🟡 MEDIUM — Registry cannot cross-check vehicle type

`AuthorizedVehicle` stores only `plate_number`, `responsible_name`, `expires_on`. There is no registered vehicle type, so a **truck carrying a car's plate is authorized without objection**. Plate cloning is not detectable.

Additionally, `AuthorizedVehicle` has **no facility scope** — the registry is global. A vehicle authorized for one facility is authorized at every facility in the system. Confirm this is the intended policy; if not, it is a security gap.

**Required change (if desired):** add optional `vehicle_type` to `AuthorizedVehicle` and flag mismatches; add facility scoping if authorization should be per-site. **Requires a migration.** Treat as a policy decision first.

---

## 4. Intrusion — Time-restriction mechanism

> **This is the item you asked to be explicitly noted.**

### 4.1 🔴 BLOCKER (documentation/ownership) — No backend mechanism evaluates the restriction window

**The configuration data exists and is fully machine-readable.** `RestrictedZoneSchedule` stores `always_restricted`, `from_time`, `to_time`, `days_of_week`, `timezone_name` (validated IANA), plus a computed `crosses_midnight`. A scoped AIKey can read it at `GET /api/v1/restricted-schedules/?camera_id=…`. Verified live earlier.

**But there is no evaluator anywhere in the backend.** A repository-wide search for `is_restricted` / `currently_restricted` / `weekday()` / `week_day` in `apps/` and `api/` returns **nothing**. The only schedule helper is the `crosses_midnight` boolean.

Consequently:

1. **No backend function answers "is this ROI restricted right now?"** The AI must implement the full evaluation itself — day-of-week matching, local-time conversion via the IANA zone, midnight-crossing windows, and DST transitions.
2. **The backend never verifies `time_restricted`.** The serializer only requires the value to be literally `true`. The AI's claim is accepted unconditionally.
3. **An intrusion event is accepted even when the ROI has no schedule at all.** Confirmed empirically: during the earlier live probe run, `GET /restricted-schedules/` returned `count=0` for the camera, and the intrusion POST still returned `201`. Nothing links an intrusion alert to a configured restricted window.

This is consistent with the authoritative specification, which lists `time_restricted` as a required **AI output** with the rule `time_restricted = true`, and does not list it among server-owned fields. **So the current implementation is spec-compliant — this is not a code defect.** It is an unowned responsibility that must be assigned explicitly before the model is connected, otherwise every team assumes the other one evaluates the schedule.

**Required action (decide, then document):**

- **(a) Keep AI-side evaluation (matches current spec):** publish a precise evaluation algorithm to the AI team covering timezone conversion, `crosses_midnight`, DST, and the `days_of_week` convention. No backend change.
- **(b) Move evaluation server-side (stronger trust model):** add a read-only `is_currently_restricted` computed field to the schedule endpoint, and optionally cross-check `time_restricted` at ingest. No migration needed — it is derived, not stored. This changes the trust model and must be authorized explicitly.

---

### 4.2 🟠 HIGH — `days_of_week` convention is not exposed in the API contract

The convention **is** documented — `docs/ai-engine.md:81` and `docs/api-specification.md:294` both state `0=Monday` through `6=Sunday`.

It is **not** in the generated OpenAPI schema: the field has no `help_text`, so a developer working from the machine-readable contract alone sees only "a list of integers 0–6". Model validation accepts any integer in `range(7)` without asserting a convention.

This matters because the three common conventions disagree: Python `weekday()` is Mon=0, JavaScript `getDay()` is Sun=0, Django `__week_day` is Sun=1. A wrong assumption shifts the entire restriction window by one day and produces silently wrong intrusion alerts.

**Required change:** add `help_text` to `RestrictedZoneSchedule.days_of_week` so the convention appears in OpenAPI. This is a schema-annotation change only — Django will generate a migration for `help_text`, so it **does require a (no-op) migration**.

---

### 4.3 🟠 HIGH — Only one schedule per ROI

`RestrictedZoneSchedule.roi` is a **`OneToOneField`**. Each ROI supports exactly one restriction window.

You cannot express, for example, "restricted 22:00–06:00 Sun–Thu **and** all day Friday–Saturday", or two separate windows in one day. The `always_restricted` flag is all-or-nothing, and the DB `CheckConstraint` forbids combining it with times or days.

**Required change (if multi-window scheduling is needed):** convert to `ForeignKey` with a related name and evaluate the union of active windows. **Requires a migration** and a change to the evaluator. Confirm the operational requirement before doing this.

---

### 4.4 🟡 MEDIUM — Window/day interaction is semantically ambiguous

For a window of `22:00 → 06:00` with `days_of_week = [0]` (Monday), it is undefined whether the restricted period is:

- Monday 22:00 → Tuesday 06:00 (window *starts* on a listed day), or
- Monday 00:00–06:00 **and** Monday 22:00–24:00 (window *clipped* to listed days).

Nothing in the model, the serializer, or the docs resolves this. Two independent implementations will disagree.

**Required change:** document the chosen interpretation in the external contract. Recommended: "the window **starts** on each listed day and may run into the following day." No code change if documented.

---

## 5. Cross-cutting fit issues (all four models)

### 5.1 🔴 BLOCKER — Naive timestamps are silently coerced to UTC

`USE_TZ = True`, `TIME_ZONE = UTC`. **Measured:** a datetime with no timezone offset is **accepted** and interpreted as UTC.

If the AI service runs in Riyadh local time and emits `2026-09-18T22:00:00` without an offset, the event is stored as **22:00 UTC = 01:00 Riyadh** — a silent 3-hour error in `detected_at`, `confirmed_at`, and `entered_roi_at`. It corrupts incident timelines, duration analytics, and any correlation with the restriction schedule, with no error raised.

**Required change:** reject naive datetimes at the serializer boundary (require an explicit offset), **or** contractually mandate that all timestamps carry an offset and add contract tests. Serializer-level validation, **no migration required**.

Accepted formats verified: ISO-8601 with `Z`, ISO-8601 with `+03:00` (correctly converted to UTC). Rejected: epoch seconds, epoch milliseconds.

---

### 5.2 🟠 HIGH — Confidence values reject more than 6 decimal places

`DecimalField(max_digits=7, decimal_places=6)` on `confidence`, `plate_confidence`, `ocr_confidence`, `vehicle_confidence`.

| Submitted | Result |
|---|---|
| `"0.9"`, `"0.91"`, `"0.910000"` | ✅ → `Decimal('0.910000')` |
| `"1.0"`, `"1.000000"`, `"0.0"` | ✅ |
| `"0.9123456"` (7 dp) | ❌ *"no more than 6 decimal places"* |
| `0.9123456789` (raw float) | ❌ *"no more than 7 digits"* |

A model that serializes a raw `float32`/`float64` score — the default for PyTorch/ONNX — **will be rejected on every event**. `duration_seconds` has the same problem at 3 decimal places: `3.1416` and `2.718281828` are both rejected.

**Required change:** contractually require the AI to round before sending (`round(conf, 6)`, `round(duration, 3)`), **or** quantize server-side in the serializer instead of rejecting. Serializer-level, **no migration required**. Rounding on the AI side is the lower-risk option.

---

### 5.3 🟠 HIGH — `bbox` units are undeclared and frame dimensions are not stored

**Measured:** both pixel coordinates (`320,180,960,720`) and normalized floats (`0.17,…,0.67`) are accepted. Only the key set (`x1,y1,x2,y2`), finiteness, non-negativity, and `x2≥x1` are enforced. There is **no** upper bound and **no** declared unit. `CameraEvent` stores **no** `frame_width`/`frame_height`/`resolution`.

A stored pixel bbox is therefore uninterpretable later — you cannot draw it on a snapshot or compare it across cameras without knowing the source resolution, which is nowhere in the record.

Also rejected: YOLO-native `{x,y,w,h}` keys and list form `[x1,y1,x2,y2]`. The AI must convert to the corner-dict form.

**Required change:** mandate **one** unit in the contract. Recommended: normalized `0.0–1.0` (resolution-independent, no extra fields, validator can then enforce `≤ 1`). If pixels are chosen instead, add `frame_width`/`frame_height` to `CameraEvent` — **that would require a migration**.

---

### 5.4 🟡 MEDIUM — `class` casing is validated loosely but stored verbatim

The rule is case-insensitive (`(object_class or "").lower() != required`), but the submitted value is stored **unchanged**:

| Submitted | Stored |
|---|---|
| `fire` | `fire` |
| `Fire` | `Fire` |
| `FIRE` | `FIRE` |
| `"  fire"` | `fire` (DRF trims) |
| `flame` | ❌ rejected |

The `object_class` column will accumulate mixed casing, so `GROUP BY object_class` and any exact-match filter or dashboard aggregation will split the same class into several buckets.

**Required change:** lowercase `object_class` in the serializer before storing. Serializer-level, **no migration required**.

---

### 5.5 🔵 INFO — `source_event_id` must be a UUID

Verified: UUID strings with or without dashes are accepted; `"1042"` and `"cam1-track7-1699999"` are rejected.

Since this field is the idempotency key, the AI pipeline must generate real UUIDs rather than counters or composite keys. Correctly declared in OpenAPI — the AI team simply needs to know. No change required.

### 5.6 🔵 INFO — `track_id` accepts integers

ByteTrack's integer track IDs are accepted and coerced to string (`7 → '7'`). No change required.

---

## 6. Summary of required changes

| # | Area | Severity | Change | Migration? |
|---|---|---|---|---|
| 1 | ANPR plate | 🔴 BLOCKER | Canonical `normalize_plate()`: strip all separators, Arabic-Indic → ASCII digits, NFKC | **Yes** (data re-normalization + collision check) |
| 2 | Timestamps | 🔴 BLOCKER | Reject naive datetimes; require explicit UTC offset | No |
| 3 | Intrusion | 🔴 BLOCKER *(ownership)* | Assign and document who evaluates the restriction window | No (unless moved server-side) |
| 4 | Vehicle type | 🟠 HIGH | Publish label mapping (`motorbike→motorcycle`, no `van` in COCO, case) or extend enum | Only if enum extended |
| 5 | Confidence | 🟠 HIGH | Require rounding to 6 dp / 3 dp, or quantize server-side | No |
| 6 | bbox | 🟠 HIGH | Declare a single unit; add frame dimensions if pixels chosen | Only if pixels chosen |
| 7 | `days_of_week` | 🟠 HIGH | Add `help_text` so `0=Monday` appears in OpenAPI | Yes (no-op) |
| 8 | Schedule | 🟠 HIGH | One window per ROI (`OneToOneField`) — convert to FK if multi-window needed | Yes, if changed |
| 9 | Raw OCR | 🟡 MEDIUM | Add `plate_number_raw` to `CameraEvent` | **Yes** |
| 10 | ANPR provenance | 🟡 MEDIUM | Add `authorized_vehicle` FK to `CameraEvent` | **Yes** |
| 11 | Registry | 🟡 MEDIUM | Optional `vehicle_type`; decide on facility scoping (registry is global today) | Yes, if changed |
| 12 | Window semantics | 🟡 MEDIUM | Document midnight-crossing + day interaction | No |
| 13 | `class` casing | 🟡 MEDIUM | Lowercase `object_class` before storing | No |

**Items 2, 3, 5, 12 and 13 need no schema change** and are the cheapest risk reduction available.

---

## 7. Confirmed as already fitting correctly

These were tested and need **no** change:

- Event-type routing and the six wire contracts — verified field-for-field against OpenAPI, zero drift.
- `plate_number` capacity consistent at 32 chars across event and registry; clean overflow error.
- Confidence bounds `0.0`–`1.0` enforced, inclusive at both ends.
- `direction` pinned per event type; `entry`/`exit` enforced.
- Tamper contract correctly minimal — no ROI, no tracking, `snapshot_path` optional.
- Server-owned ANPR authorization — both forging (`true`) and understating (`false`) are rejected.
- Idempotency on `credential + source_event_id` — `201` → `200` → `409`, no duplicate alert, notification, or audit row.
- Camera/facility scope enforcement, snapshot path binding, and traversal rejection.
- `track_id` integer coercion; `confirmed_at ≥ detected_at` ordering.
- ROI polygon, virtual line, and schedule config all machine-readable over AIKey.

---

## 8. Note on this document

No code, schema, migration, audit, frontend, or AI-integration behaviour was modified. The only file added by this analysis is this report. The backend remains at commit `96a8add` with its pre-existing working-tree state, plus this file as a new untracked document.
