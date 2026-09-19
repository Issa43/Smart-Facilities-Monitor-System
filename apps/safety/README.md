This application owns external safety and disaster alerting for projects
("الإنذارات والسلامة"): normalized external `HazardEvent` facts, project-scoped
`ProjectSafetyAlert` records, the deterministic safety policy, geospatial
matching, the human alert workflow, and their migrations and tests.

Principle: an external provider reports facts; SFLMS policy decides whether a
project is affected; a responsible human manager decides what to do. The system
never suspends, evacuates, cancels, or messages workers on its own, never closes
an alert because a provider withdrew or stopped reporting an event, and never
infers a hazard from missing data.

## Current scope

Implemented: models, policy, geo matching, ingestion and workflow services,
recipient scoping, durable notifications, semantic audit, permissions,
settings, USGS and GDACS provider adapters, Celery Beat polling, and the human
REST API under `/api/v1/safety/` (`api/v1/safety/`, documented in
`docs/api-specification.md`). Not implemented yet: frontend, Telegram, and
weather.

## Providers and polling

Adapters in `providers/` only translate a provider response into validated
`NormalizedHazardEvent` values. They make no policy decisions, create no
alerts, and send no notifications. `polling.py` hands their output to
`ingest_hazard_events`, which remains the only path that creates hazard events,
alerts, audit entries, and notifications.

| Task | Schedule | Source |
|---|---|---|
| `safety.poll_usgs_earthquakes` | every `SAFETY_USGS_POLL_SECONDS` (300 s) | USGS `2.5_day.geojson` summary feed |
| `safety.poll_gdacs_events` | every `SAFETY_GDACS_POLL_SECONDS` (900 s) | GDACS `EVENTS4APP` event list |

Each poll checks, in order: the provider flag, both alerting kill switches (the
poll exits before any network call if either is off), a rate-limit backoff
marker, and a non-blocking cache lock that skips overlapping runs. Beat
messages expire after one interval, and task time limits end before the lock
expires.

HTTP (`providers/http.py`, standard library only): https only, a fixed host
allowlist checked before connecting and on redirects, explicit timeout and
overall read deadline, response size cap, JSON content check, no credentials,
and sanitized error codes that never include URLs or bodies. Provider page
links in payloads are stored only if they pass the host allowlist and are never
fetched.

Failure behavior:

- Network error, timeout, or HTTP 5xx: nothing is written; the task retries at
  most `SAFETY_PROVIDER_MAX_RETRIES` times with bounded backoff, then waits for
  the next scheduled run.
- HTTP 4xx, disallowed endpoint, wrong content type, oversized or undecodable
  body, or an invalid feed structure: the whole response is rejected, nothing is
  written, and it is not retried.
- HTTP 429: a cache backoff (at least one interval, at most one hour) skips
  polls until it expires.
- A malformed individual record is counted and skipped; valid records in the
  same response are still ingested.
- Unexpected errors propagate to Celery after the lock is released; per-event
  transactions keep previously committed alerts intact.

Each poll logs one line with provider, status, and counters (records received,
normalized, malformed, unsupported, reconciled, deferred to USGS, plus
ingestion counts), and
stores the last outcome in the cache (`safety:provider:<code>:last-poll`,
`last-success`).

Identity and revisions:

- USGS: `provider_event_id` is the feature `id`; `properties.updated` is the
  revision timestamp; `status: "deleted"` becomes `withdrawn`. Non-earthquake
  types (for example quarry blasts) are skipped. PAGER `yellow` has no
  equivalent alert level and is kept only in the payload.
- GDACS: `provider_event_id` is `<eventtype>:<eventid>`; `datemodified` is the
  revision timestamp; the more severe of the event and current-episode alert
  levels is used; `iscurrent: false` becomes `expired`; naive timestamps are
  treated as UTC. Droughts and unknown types are skipped.

Earthquake source separation: USGS is the authoritative earthquake source.
While `SAFETY_USGS_ENABLED` is on, every GDACS earthquake is skipped in the
adapter before ingestion, counted as `records_deferred_to_usgs`, and logged with
its public GDACS id (`EQ:<eventid>`). If a record also cites a USGS/NEIC
network-prefixed event id (for example `us7000abcd`), that pair is logged and
counted as reconciled. A controlled live probe showed GDACS earthquakes cite
`source: NEIC` with an empty `sourceid`, so the two feeds cannot be correlated
reliably; no coordinate, time, or magnitude heuristic is used. The decision
follows the configuration flag, not USGS runtime availability, so a USGS outage
never re-enables duplicate earthquake ingestion (earthquakes are simply not
monitored until USGS recovers). With `SAFETY_USGS_ENABLED` off, GDACS
earthquakes are ingested as their own `gdacs` events. Cyclone, flood, volcano,
and wildfire events are unaffected. The GDACS field mapping was confirmed
against one live `EVENTS4APP` response (100 events, none malformed).

## Kill switches (both default off)

Alert creation requires `settings.SAFETY_ALERTS_ENABLED` (environment) and the
`safety.externalAlerts` SystemSetting. While either is off,
`ingest_hazard_events` returns `enabled=False` and writes nothing.

## Modules

- `models.py` — `HazardEvent` (unique `provider` + `provider_event_id`,
  coordinate/enum CHECKs, https provider-host `source_url`, sanitized payload of
  at most 32 KB) and `ProjectSafetyAlert` (unique `project` + `hazard_event`,
  immutable project coordinate snapshot, status/field consistency CHECKs, no
  hard delete).
- `policy.py` — `DEFAULT_POLICY` (illustrative thresholds, not approved HSE
  values), strict validation of the `safety.hazardPolicy` override, safe loading
  that falls back to defaults and logs only an error count, deterministic
  `evaluate()` returning severity, rule code, recommended action, and policy
  version, and the kill-switch check. Monitored project statuses are
  `in_progress` and `operational`; `planning` is not monitored.
- `geo.py` — haversine distance (Earth radius 6371.0088 km), conservative
  bounding boxes that handle the antimeridian and poles, and a SQL prefilter
  plus exact-distance project matcher. Projects without coordinates never match.
  Also the optional area-geometry mode described below.
- `services.py` — `NormalizedHazardEvent` ingestion contract and
  `ingest_hazard_events()`, plus the workflow services.
- `recipients.py` — the single scope rule used for notifications and for
  authorizing workflow actions.
- `notifications.py` — post-commit fan-out through the shared
  `notify_users()`.
- `telegram.py` — the outbound-only Telegram client (`sendMessage` and nothing
  else), with sanitized failure codes so the bot token in the request URL can
  never reach an exception, a log record, or a stored field.
- `telegram_delivery.py` — the decision event key, the Arabic message builder,
  and idempotent creation of delivery rows after commit.
- `telegram_tasks.py` — the bounded delivery task. Kept out of `tasks.py` so
  that module stays provider polling only; registered from `SafetyConfig.ready`
  because Celery autodiscovery imports only `tasks`.
- `admin.py` — the only place a Telegram destination can be created.

## Ingestion rules

- Each event runs in its own transaction; invalid events are skipped and counted.
- A new event is stored only if it is active, its hazard type has policy rules,
  and at least one monitored project with coordinates is within the maximum
  policy radius.
- An identical `provider_updated_at` only refreshes `last_seen_at`; an older one
  is ignored and never overwrites newer state; a newer one increments `revision`.
- Events older than the hazard's `max_event_age_hours` create no new alerts.
  Earthquakes are aged from `occurred_at` only, so a late provider revision of
  an old earthquake creates no new alert. Ongoing hazards (cyclone, flood,
  volcano, wildfire) are aged from their latest provider activity, the later
  of `occurred_at` and `provider_updated_at`, using the same
  `max_event_age_hours`. An old event without a revision inside that window is
  stale; an old but still-active event revised inside it is evaluated
  normally. Revisions are recognized only when `provider_updated_at` increases,
  so repeated identical provider data never re-triggers evaluation.
- Open alerts are re-evaluated against their stored coordinate snapshot and are
  escalated only to a higher severity. Downgrades never change an alert.
- A withdrawal marks open alerts with `hazard_withdrawn_at` without changing
  their status.

## Workflow

`new → acknowledged → actioned → closed`, and `new | acknowledged → dismissed`.
`available_actions(alert)` returns the actions allowed by status. Deciding
`other` requires notes; dismissal requires a reason. Decisions can be revised
while the alert is `actioned`. Illegal transitions raise `ValidationError`;
actors outside scope or without `safety.manage` raise `PermissionDenied`.

## Human decision workflow (the business rule)

A hazard is information. It never becomes an instruction on its own: nothing is
stopped, suspended, evacuated, messaged or executed because a provider reported
something. A responsible manager proposes a protective action and the General
Manager rules on it.

```
Hazard provider (MHEWS / GDACS / USGS)
  -> ProjectSafetyAlert                      information only
  -> CM and OM see it, each within their own scope
  -> CM proposes WORKER_PROTECTION           |  OM proposes ASSET_PROTECTION
  -> GM / Super Admin reviews
     APPROVE                                     REJECT
       worker: alert -> actioned,                  nothing executes,
               instruction sent by the SFLMS       nothing is sent,
               Telegram bot to the affected        the proposer is notified
               project's channel(s)                with the reason
       asset:  decision recorded + audited
```

Who may do what (`SafetyActionProposal`):

| | propose worker | propose asset | approve / reject |
|---|---|---|---|
| Construction Manager | yes (own projects) | no | no |
| Operations Manager | no | yes (own facility) | no |
| GM / Super Admin | **no** | **no** | yes (global) |
| Security Officer | no | no | no |

**The General Manager cannot create proposals.** `user_can_propose` refuses
anyone who holds approval authority, so `available_proposal_types` is `[]` for
them and the API answers 403. This is why the permission grant alone is not
enough: `user_has_permission` short-circuits to True for Super Admin, which
would otherwise hand the approver both proposal permissions. Separation of
duties is therefore structural — an approver has nothing of their own to rule
on — and self-approval is refused besides.

Proposal lifecycle: `pending_manager_review -> approved | rejected`. A ruling is
final; a rejected proposal cannot be reopened, and approving twice answers 409
so no second dispatch is possible. At most one open proposal of each kind may
exist per alert. A proposal carries the hazard, the affected project (and
facility assets for asset protection), the proposed action, a required
justification, an optional effective window, and an optional worker scope — all
of which the approver sees before ruling.

Raising a proposal acknowledges the alert if it was still `new`, because the
alert lifecycle requires an acknowledgement before `actioned` and a manager who
has read the hazard closely enough to propose a response has plainly seen it.

`/decide/` remains, but only for the approver: recording a final decision is
what reaches people, so it carries the same authority as approving a proposal.
CM and OM receive 403 there.

## Scope and permissions

- Construction Managers: active `ProjectAssignment` on the project.
- Operations Managers: active `FacilityAssignment` on the project's active
  facility. Projects without a facility have no Operations scope.
- Super Admin: all alerts.
- Security Officers have no safety alert access.

Permissions `safety.view`, `safety.manage`, and `safety.broadcast` are seeded
for Construction and Operations Managers (`users.0005`); Super Admin bypasses
permission checks. `safety.propose_worker_protection` is seeded for Construction Managers and
`safety.propose_asset_protection` for Operations Managers (`users.0006`).
`safety.approve` is granted to no role, so it resolves only through the
Super Admin branch and is the General Manager's approval authority.

## Notifications

Category `safety`. Recipients are scoped managers with `safety.view`, plus
Super Admins for `high` and `critical` severities. Deduplication keys are
`safety-alert:{alert_id}:{severity}` (one additional notification per recipient
on escalation) and `safety-alert:{alert_id}:withdrawn`. Delivery honors
`notify.safetyAlerts` and the existing `critical_alerts` preference. Delivery
runs after commit; a failure is logged and never rolls back an alert.

## MHEWS (Syria) — official weather warnings

Source: Ministry of Emergency and Disaster Management, Multi-Hazard Early
Warning System. RSS discovery index `https://climweb.med.gov.sy/api/cap/rss.xml`
pointing at CAP 1.2 documents on the same host, sender `mhews@med.gov.sy`,
public domain, no credentials. **Disabled by default** behind
`SAFETY_WEATHER_ENABLED`, and additionally gated by both existing Safety kill
switches; while off, the poll exits before any request.

This is a warning feed, not a weather feed. Nothing becomes a Safety alert
because it is hot, wet, windy or dusty — only because an authority issued an
official warning that satisfies the existing policy.

**Adapter** (`providers/mhews.py`) — the RSS index is only for discovery; the
CAP document is the authority. Only links on the approved host are fetched, no
link *inside* a CAP document is ever dereferenced, XML `DOCTYPE` declarations
are refused, and the shared bounded transport enforces https, host allowlist,
timeout, byte cap and redirect policy. A document is rejected unless its sender
is approved, its `status` is `Actual` and its `msgType` is Alert, Update or
Cancel; unknown values fail closed.

**Event codes.** Hazard type comes from the WMO OET `eventCode` only — never
from headline or description text.

| OET | Event | Maps to |
|---|---|---|
| OET-079 | flash flood | `flood` |
| OET-098 | high temperature / heat wave | `extreme_heat` |
| OET-170 | dust / sand storm | `dust_storm` |
| OET-103 | rising water level / flow (`Infra`) | **unmapped** — hydrological infrastructure, not meteorological flooding |
| OET-100 | high waves | **unmapped** — marine, outside construction scope |

Thunderstorm and heavy rainfall are **unmapped**: no OET code for either
appears in the feed, and none was invented. `heavy_rain` already exists in the
taxonomy, so no new value is needed once a code is verified.

**Severity** is deliberately lossy, by authorized decision:

| CAP | `alert_level` | Note |
|---|---|---|
| Extreme | `red` | **collapses with Severe** |
| Severe | `red` | |
| Moderate | `orange` | |
| Minor | `green` | matches no default tier, so raises no alert |
| Unknown | *(none)* | never actionable |

The original CAP value is preserved in `provider_severity`, so nothing is lost
from the record — only from the normalized level used by policy.

**Policy.** `extreme_heat` and `dust_storm` are evaluated on `min_alert_level`,
exactly like flood, cyclone, volcano and wildfire: the criterion reads the
severity of an official warning. **No meteorological threshold exists** — the
platform never measures temperature, visibility, wind or rainfall. As with
every other entry in `DEFAULT_POLICY`, the severity and action are illustrative
defaults that operators replace through `safety.hazardPolicy`.

**Identity.** One logical hazard per warning chain. An Update carries a new CAP
identifier and a `references` triple; the adapter walks the chain to the root
Alert identifier and stores that as `provider_event_id`, so an Update revises
the existing `HazardEvent` instead of creating a second one. Recursion is
bounded and cycle-safe, references from unapproved senders are ignored, and a
Cancel resolves to the same root and withdraws through the existing
`provider_status` semantics — the human workflow still owns any open alert.

**Geometry.** MHEWS publishes polygons only. CAP positions are
`latitude,longitude` and are swapped into the canonical `[longitude, latitude]`
order on the way in. All polygons are preserved as disjoint MultiPolygon
components and matched by exact containment (see below). A malformed polygon
rejects the whole alert rather than producing partial coverage. The stored
`latitude`/`longitude` is a display and audit reference only: it is never used
to match projects and no radius is derived from it.

## Geometry: point+radius, plus optional warned areas

A hazard is matched to projects in exactly one of two modes. They never mix.

**Point + radius (unchanged, the default).** `latitude`, `longitude` and
`radius_km`, matched by SQL bounding box then exact haversine distance, with
`distance_km <= radius` inclusive. This is what USGS and GDACS use and its
behaviour is untouched.

**Authoritative area (optional).** `HazardEvent.area_polygons` holds the warned
area for providers that publish one, for example an official CAP warning. When
it is set, matching is exact point-in-polygon containment; `radius_km` is not
used to match, and `latitude`/`longitude` remain the event's reference point
for display and audit only. `distance_km` on the resulting alert is `0.00`,
meaning *inside the warned area* rather than a measured distance from a centre.

- **Storage** — canonical GeoJSON MultiPolygon coordinates, validated and
  normalized in `clean()` (like `payload`, application-level, no DB CHECK).
  A single Polygon is promoted to a one-element MultiPolygon, and unclosed
  rings are closed, so every reader sees one shape.
- **Coordinate convention** — positions are **`[longitude, latitude]`**
  (GeoJSON, RFC 7946), deliberately the opposite of the `(latitude, longitude)`
  argument order used elsewhere in `geo.py`. Every position is range-checked,
  which rejects most accidentally swapped pairs.
- **Rings** — the first ring of a polygon is the exterior, any others are
  holes. Inside the exterior and outside every hole matches; inside a hole does
  not. Ring winding direction does not affect matching.
- **MultiPolygon** — a project matches if it lies inside any component.
  Disjoint components never merge.
- **Boundary rule** — a point lying exactly on any ring, exterior or hole, is
  treated as **inside** the warned area. Warning is the safe direction at an
  edge, and it matches the inclusive `distance <= radius` rule above. The
  comparison uses a 1e-9 degree tolerance so the result never depends on
  floating-point accident.
- **Bounding box** — only a SQL prefilter. Containment is always confirmed
  exactly in Python, so a project inside the box but outside the polygon does
  not match. There is no centroid, bounding-circle, bounding-box or
  nearest-point approximation anywhere in this path.
- **Fail closed** — missing, non-numeric, NaN, infinite, out-of-range,
  degenerate, oversized or structurally invalid geometry raises
  `geo.InvalidGeometry` and matches nothing. Bounds: 64 polygons, 128 rings,
  4000 positions per ring, 20000 positions total.
- **Not supported** — antimeridian-crossing areas. A polygon spanning more than
  180° of longitude is rejected rather than approximated; the existing
  point+radius bounding box still handles the antimeridian for circles.

No PostGIS, no GeoDjango, no GIS dependency: the implementation is pure Python
plus a `JSONField`.

## Telegram (outbound only, disabled by default)

The SFLMS Telegram **bot** is the sender; no human account is involved, and a
General Manager never opens Telegram, copies text or picks recipients. Approval
is one action and the platform does the rest.

**The one trigger.** Outbound worker instructions have exactly one cause: a GM
approving a `WORKER_PROTECTION` proposal. Ingestion, alert creation,
acknowledgement, escalation, withdrawal, polling, cron, the AI engine, proposal
creation, any rejection, asset-protection approval and the frontend never reach
this module. Dispatch is scheduled with `transaction.on_commit(..., robust=True)`,
so no Telegram outcome can roll a ruling back.

```
GM clicks "موافقة وإرسال القرار"
  -> proposal recorded APPROVED (+ audit)
  -> SafetyTelegramDelivery rows created, one per destination
  -> deliver_safety_telegram_message queued on Celery
  -> worker calls the Telegram Bot API sendMessage
  -> the affected project's channel(s) receive the approved decision
```

**Project -> destination.** `ProjectTelegramDestination` links a project to a
numeric chat/group/channel id, with an optional display name and an enabled
flag. Routing is the whole rule: a decision reaches its own project's enabled
destinations and nothing else. Project A's decision never reaches Project B, and
there is no global fallback group. A project with no destination produces no
rows and logs a warning, so "unreachable" is visible rather than looking like a
delivery that quietly succeeded.

Destinations are created only in Django Admin. There is no REST endpoint, no
self-service flow and no import command, so a chat id can never be set from the
frontend or from a provider payload, and none is ever hard-coded.

`SafetyTelegramRecipient` is a separate audience: a responsible manager's own
destination for recorded-decision messages. One routing rule per audience.

**Delivery state is honest.** `SafetyTelegramDelivery` is unique on
`(alert, recipient, event_key)` and on `(alert, project_destination, event_key)`,
and a check constraint requires exactly one of the two audiences per row. The
event key is derived from persisted approval state, so a replayed Celery task, a
duplicated commit hook or a repeated approval all collapse onto the same row and
cannot produce a second message. A row is `sent` only when the Telegram API
accepted the request and returned a message id; anything else is `failed`
(with a sanitized code) or `skipped` (`telegram_not_configured`,
`telegram_recipient_disabled`, `telegram_disabled`). Nothing is ever recorded as
sent because the switch was off.

**Configuration** (backend only, never in frontend env or source):

| Variable | Meaning |
|---|---|
| `SAFETY_TELEGRAM_ENABLED` | Master switch. Default `False`. |
| `SAFETY_TELEGRAM_BOT_TOKEN` | Bot token from BotFather. Secret; never committed. |
| `SAFETY_TELEGRAM_TIMEOUT_SECONDS` | Per-request timeout (1-30, default 10). |
| `SAFETY_TELEGRAM_MAX_RETRIES` | Retries for retryable failures (0-5, default 3). |
| `SAFETY_TELEGRAM_MAX_MESSAGE_CHARS` | Message bound (500-4096, default 3500). |

The token appears only in the outbound request URL. urllib attaches that URL to
its exceptions, so every failure is re-raised as a sanitized `TelegramError`
with `from None`, and originals are never logged. The client is https-only,
refuses credentialed or redirecting endpoints, and has no webhook, no
`getUpdates` and no command handling: nothing Telegram returns can change a
safety alert.

## Audit

System actions (`actor=None`): `safety_alert.created`, `safety_alert.escalated`,
`safety_alert.hazard_withdrawn`. Human actions: `safety_alert.acknowledged`,
`safety_alert.action_decided`, `safety_alert.dismissed`, `safety_alert.closed`.
Audit dictionaries contain states, identifiers, and note lengths only, never
note text, provider payloads, or credentials.

## Settings

Seeded by `common.0003`: `safety.externalAlerts=false`,
`notify.safetyAlerts=true`, `safety.hazardPolicy={}`. The settings API validates
these keys through `apps.safety.policy.validate_safety_setting`.
