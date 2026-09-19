from unittest.mock import patch

import pytest
from celery.exceptions import Retry
from django.conf import settings as django_settings

from apps.safety import polling, tasks
from config.celery import app
from config.settings.base import _bounded_int_setting


def test_beat_schedules_use_existing_celery_beat_with_bounded_expiry():
    schedule = django_settings.CELERY_BEAT_SCHEDULE
    assert schedule["safety-poll-usgs-earthquakes"] == {
        "task": "safety.poll_usgs_earthquakes",
        "schedule": 300.0,
        "options": {"expires": 300},
    }
    assert schedule["safety-poll-gdacs-events"] == {
        "task": "safety.poll_gdacs_events",
        "schedule": 900.0,
        "options": {"expires": 900},
    }
    # Existing schedules are preserved.
    assert "notify-critical-security-alerts" in schedule
    assert "recover-queued-push-deliveries" in schedule


def test_tasks_are_registered_with_the_existing_celery_app():
    assert "safety.poll_usgs_earthquakes" in app.tasks
    assert "safety.poll_gdacs_events" in app.tasks


@pytest.mark.parametrize("task,code", [(tasks.poll_usgs_earthquakes, "usgs"), (tasks.poll_gdacs_events, "gdacs")])
def test_task_time_limits_stay_inside_the_overlap_lock(task, code):
    assert task.soft_time_limit < task.time_limit < polling.lock_ttl_seconds(code)
    assert polling.lock_ttl_seconds(code) <= max(polling.poll_interval_seconds(code), 90)


def test_poll_settings_are_clamped(monkeypatch):
    monkeypatch.setenv("SAFETY_TEST_INTERVAL", "5")
    assert _bounded_int_setting("SAFETY_TEST_INTERVAL", 300, 60, 3600) == 60
    monkeypatch.setenv("SAFETY_TEST_INTERVAL", "999999")
    assert _bounded_int_setting("SAFETY_TEST_INTERVAL", 300, 60, 3600) == 3600


def _outcome(status, retryable):
    return polling.PollOutcome(provider="usgs", status=status, retryable=retryable)


def test_retryable_unavailability_retries_with_bounded_backoff(settings):
    settings.SAFETY_PROVIDER_MAX_RETRIES = 2
    with patch.object(tasks, "run_provider_poll", return_value=_outcome("unavailable", True)):
        with patch.object(tasks.poll_usgs_earthquakes, "retry", side_effect=Retry()) as retry:
            with pytest.raises(Retry):
                tasks.poll_usgs_earthquakes.run()
    retry.assert_called_once_with(countdown=30)


def test_retries_stop_at_the_configured_limit(settings):
    settings.SAFETY_PROVIDER_MAX_RETRIES = 2
    tasks.poll_usgs_earthquakes.push_request(retries=2)
    try:
        with patch.object(tasks, "run_provider_poll", return_value=_outcome("unavailable", True)):
            with patch.object(tasks.poll_usgs_earthquakes, "retry") as retry:
                result = tasks.poll_usgs_earthquakes.run()
    finally:
        tasks.poll_usgs_earthquakes.pop_request()
    retry.assert_not_called()
    assert result["status"] == "unavailable"


@pytest.mark.parametrize(
    "status,retryable,max_retries",
    [("malformed", False, 2), ("safety_disabled", False, 2), ("unavailable", False, 2), ("unavailable", True, 0)],
)
def test_non_retryable_outcomes_are_never_retried(settings, status, retryable, max_retries):
    settings.SAFETY_PROVIDER_MAX_RETRIES = max_retries
    with patch.object(tasks, "run_provider_poll", return_value=_outcome(status, retryable)):
        with patch.object(tasks.poll_gdacs_events, "retry") as retry:
            result = tasks.poll_gdacs_events.run()
    retry.assert_not_called()
    assert result["status"] == status


def test_retry_countdown_is_bounded():
    assert [polling.retry_countdown_seconds("usgs", n) for n in range(4)] == [30, 60, 100, 100]
    assert max(polling.retry_countdown_seconds("gdacs", n) for n in range(10)) == 300


@pytest.mark.django_db
def test_task_run_while_disabled_is_a_safe_no_op(settings):
    settings.SAFETY_ALERTS_ENABLED = False
    with patch("apps.safety.providers.usgs.fetch_json") as fetch_json:
        result = tasks.poll_usgs_earthquakes.run()
    fetch_json.assert_not_called()
    assert result["status"] == "safety_disabled"
