"""Provider polling orchestration shared by the Celery tasks.

Order of checks for every poll:

1. Provider polling flag (``SAFETY_<PROVIDER>_ENABLED``).
2. Both Safety kill switches. When alerting is disabled the poll exits before
   any network call, so "provider polling enabled" never implies alerting.
3. Rate-limit backoff marker.
4. Non-blocking overlap lock in the shared cache (Redis in deployments).
5. Fetch and normalize, then hand events to ``ingest_hazard_events``.

Polling never notifies, messages, or changes project state directly. Durable
manager notifications happen only inside the existing Safety ingestion
service.
"""

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from . import policy as safety_policy
from .providers.base import MalformedProviderPayload, ProviderRateLimited, ProviderUnavailable
from .services import ingest_hazard_events


logger = logging.getLogger(__name__)

MAX_LOGGED_RECONCILIATIONS = 50
LAST_POLL_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_BACKOFF_SECONDS = 3600
INGESTION_COUNTERS = (
    "events_created",
    "events_updated",
    "events_unchanged",
    "events_ignored",
    "stale_updates_ignored",
    "invalid_skipped",
    "alerts_created",
    "alerts_escalated",
    "alerts_withdrawn",
)


@dataclass
class PollOutcome:
    provider: str
    status: str
    retryable: bool = False
    error_code: str = ""
    counters: dict = field(default_factory=dict)

    def as_dict(self):
        return asdict(self)


def poll_interval_seconds(provider_code):
    return {
        "usgs": settings.SAFETY_USGS_POLL_SECONDS,
        "gdacs": settings.SAFETY_GDACS_POLL_SECONDS,
        "mhews": settings.SAFETY_MHEWS_POLL_SECONDS,
    }[provider_code]


def lock_ttl_seconds(provider_code):
    """Lock lifetime; always longer than the task hard time limit."""

    return max(poll_interval_seconds(provider_code) - 30, 90)


def task_time_limits(provider_code):
    ttl = lock_ttl_seconds(provider_code)
    return {"soft_time_limit": ttl - 30, "time_limit": ttl - 15}


def retry_countdown_seconds(provider_code, retries):
    return min(30 * (2 ** retries), max(poll_interval_seconds(provider_code) // 3, 30))


def _key(provider_code, suffix):
    return f"safety:provider:{provider_code}:{suffix}"


def _acquire_lock(provider_code):
    token = uuid.uuid4().hex
    if cache.add(_key(provider_code, "poll-lock"), token, timeout=lock_ttl_seconds(provider_code)):
        return token
    return None


def _release_lock(provider_code, token):
    key = _key(provider_code, "poll-lock")
    if cache.get(key) == token:
        cache.delete(key)


def _format_counters(counters):
    return " ".join(f"{name}={value}" for name, value in counters.items())


def _record(outcome, started):
    outcome.counters["duration_ms"] = int((time.monotonic() - started) * 1000)
    snapshot = {**outcome.as_dict(), "finished_at": timezone.now().isoformat()}
    try:
        cache.set(_key(outcome.provider, "last-poll"), snapshot, timeout=LAST_POLL_TTL_SECONDS)
        if outcome.status == "completed":
            cache.set(_key(outcome.provider, "last-success"), snapshot["finished_at"], timeout=LAST_POLL_TTL_SECONDS)
    except Exception:
        logger.warning("Safety provider poll status could not be cached provider=%s", outcome.provider)
    return outcome


def run_provider_poll(provider, *, now=None):
    code = provider.code
    started = time.monotonic()

    if not provider.enabled():
        logger.debug("Safety provider poll skipped provider=%s status=provider_disabled", code)
        return PollOutcome(provider=code, status="provider_disabled")
    if not safety_policy.alert_creation_enabled():
        logger.debug("Safety provider poll skipped provider=%s status=safety_disabled", code)
        return PollOutcome(provider=code, status="safety_disabled")
    if cache.get(_key(code, "backoff-until")):
        logger.info("Safety provider poll skipped provider=%s status=backoff", code)
        return PollOutcome(provider=code, status="backoff")

    token = _acquire_lock(code)
    if token is None:
        logger.info("Safety provider poll skipped provider=%s status=locked", code)
        return PollOutcome(provider=code, status="locked")

    try:
        try:
            batch = provider.fetch()
        except ProviderRateLimited as exc:
            backoff = min(max(exc.retry_after_seconds, poll_interval_seconds(code)), MAX_BACKOFF_SECONDS)
            cache.set(_key(code, "backoff-until"), int(time.time()) + backoff, timeout=backoff)
            logger.warning("Safety provider poll failed provider=%s status=rate_limited backoff_seconds=%s", code, backoff)
            return _record(PollOutcome(provider=code, status="rate_limited", error_code=exc.code), started)
        except ProviderUnavailable as exc:
            logger.warning(
                "Safety provider poll failed provider=%s status=unavailable code=%s retryable=%s",
                code,
                exc.code,
                exc.retryable,
            )
            return _record(
                PollOutcome(provider=code, status="unavailable", retryable=exc.retryable, error_code=exc.code),
                started,
            )
        except MalformedProviderPayload as exc:
            logger.warning("Safety provider poll rejected provider=%s status=malformed code=%s", code, exc.code)
            return _record(PollOutcome(provider=code, status="malformed", error_code=exc.code), started)

        if batch.records_deferred_to_usgs:
            logger.info(
                "Safety provider records deferred to USGS provider=%s count=%s gdacs_event_ids=%s",
                code,
                batch.records_deferred_to_usgs,
                ",".join(batch.deferred_event_ids[:MAX_LOGGED_RECONCILIATIONS]),
            )
        for item in batch.reconciliations[:MAX_LOGGED_RECONCILIATIONS]:
            logger.info(
                "Safety provider record reconciled provider=%s gdacs_event_id=%s usgs_event_id=%s",
                code,
                item["gdacs_event_id"],
                item["usgs_event_id"],
            )

        result = ingest_hazard_events(batch.events, now=now)
        counters = {
            "records_received": batch.records_received,
            "records_normalized": len(batch.events),
            "records_malformed": batch.records_malformed,
            "records_unsupported": batch.records_unsupported,
            "records_reconciled": batch.records_reconciled,
            "records_deferred_to_usgs": batch.records_deferred_to_usgs,
            **{name: getattr(result, name) for name in INGESTION_COUNTERS},
        }
        if not result.enabled:
            # A kill switch was turned off between the check and ingestion.
            return _record(PollOutcome(provider=code, status="safety_disabled", counters=counters), started)
        outcome = _record(PollOutcome(provider=code, status="completed", counters=counters), started)
        logger.info("Safety provider poll completed provider=%s %s", code, _format_counters(outcome.counters))
        return outcome
    finally:
        _release_lock(code, token)
