"""Celery Beat entry points for external hazard provider polling.

Tasks only orchestrate: fetch, normalize, and hand events to the Safety
ingestion service. Retries are bounded and apply only to retryable provider
unavailability; malformed payloads and disabled states are never retried.
"""

from celery import shared_task
from django.conf import settings

from .polling import retry_countdown_seconds, run_provider_poll, task_time_limits
from .providers.gdacs import GdacsProvider
from .providers.mhews import MhewsWarningProvider
from .providers.usgs import UsgsEarthquakeProvider


# Decorator ceiling; the configured SAFETY_PROVIDER_MAX_RETRIES (0-3) applies.
TASK_MAX_RETRIES = 3


def _poll(task, provider):
    outcome = run_provider_poll(provider)
    retries = task.request.retries or 0
    if outcome.retryable and retries < settings.SAFETY_PROVIDER_MAX_RETRIES:
        raise task.retry(countdown=retry_countdown_seconds(provider.code, retries))
    return outcome.as_dict()


@shared_task(
    bind=True,
    name="safety.poll_usgs_earthquakes",
    max_retries=TASK_MAX_RETRIES,
    **task_time_limits("usgs"),
)
def poll_usgs_earthquakes(self):
    return _poll(self, UsgsEarthquakeProvider())


@shared_task(
    bind=True,
    name="safety.poll_gdacs_events",
    max_retries=TASK_MAX_RETRIES,
    **task_time_limits("gdacs"),
)
def poll_gdacs_events(self):
    return _poll(self, GdacsProvider())


@shared_task(
    bind=True,
    name="safety.poll_mhews_warnings",
    max_retries=TASK_MAX_RETRIES,
    **task_time_limits("mhews"),
)
def poll_mhews_warnings(self):
    """Official Syrian warnings. Exits before any request while disabled."""

    return _poll(self, MhewsWarningProvider())
