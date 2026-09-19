import inspect
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.cache import cache

from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from apps.projects.models import Project
from apps.safety import polling, tasks
from apps.safety.models import HazardEvent, ProjectSafetyAlert
from apps.safety.providers import gdacs, usgs
from apps.safety.providers.base import MalformedProviderPayload, ProviderRateLimited, ProviderUnavailable
from apps.safety.tests.helpers import (
    NOW,
    assign_construction_manager,
    enable_alerts,
    later,
    make_project,
    make_user,
    set_setting,
)
from apps.safety.tests.provider_samples import gdacs_feature, gdacs_feed, usgs_feature, usgs_feed
from apps.users.models import Role


pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def project(super_admin_user):
    site = make_project(super_admin_user)
    manager = make_user(Role.CONSTRUCTION_MANAGER, "cm")
    assign_construction_manager(site, manager, super_admin_user)
    site.manager = manager
    return site


@pytest.fixture
def enabled(settings):
    enable_alerts(settings)


def poll_usgs(document, now=NOW):
    with patch.object(usgs, "fetch_json", return_value=document) as fetch_json:
        outcome = polling.run_provider_poll(usgs.UsgsEarthquakeProvider(), now=now)
    return outcome, fetch_json


def poll_gdacs(document, now=NOW):
    with patch.object(gdacs, "fetch_json", return_value=document) as fetch_json:
        outcome = polling.run_provider_poll(gdacs.GdacsProvider(), now=now)
    return outcome, fetch_json


def lock_key(code):
    return f"safety:provider:{code}:poll-lock"


def test_disabled_safety_exits_before_any_network_call(settings, project):
    settings.SAFETY_ALERTS_ENABLED = False
    set_setting("safety.externalAlerts", True)
    outcome, fetch_json = poll_usgs(usgs_feed(usgs_feature()))
    assert outcome.status == "safety_disabled"
    fetch_json.assert_not_called()

    settings.SAFETY_ALERTS_ENABLED = True
    set_setting("safety.externalAlerts", False)
    outcome, fetch_json = poll_gdacs(gdacs_feed(gdacs_feature()))
    assert outcome.status == "safety_disabled"
    fetch_json.assert_not_called()
    assert HazardEvent.all_objects.count() == 0


def test_provider_flag_disables_polling_independently(settings, enabled, project):
    settings.SAFETY_USGS_ENABLED = False
    outcome, fetch_json = poll_usgs(usgs_feed(usgs_feature()))
    assert outcome.status == "provider_disabled"
    fetch_json.assert_not_called()


def test_usgs_poll_ingests_through_safety_domain_with_provider_identity(enabled, project):
    outcome, fetch_json = poll_usgs(usgs_feed(usgs_feature(), usgs_feature("us1far", latitude=-40.0, longitude=100.0)))

    fetch_json.assert_called_once()
    assert outcome.status == "completed"
    assert outcome.counters["records_received"] == 2
    assert outcome.counters["events_created"] == 1 and outcome.counters["events_ignored"] == 1
    assert outcome.counters["alerts_created"] == 1
    event = HazardEvent.objects.get()
    assert (event.provider, event.provider_event_id) == ("usgs", "us7000test")
    alert = ProjectSafetyAlert.objects.get()
    assert AuditLog.objects.get(action="safety_alert.created").after["provider"] == "usgs"
    assert alert.severity == "high"
    assert cache.get(lock_key("usgs")) is None
    assert cache.get("safety:provider:usgs:last-poll")["status"] == "completed"
    assert cache.get("safety:provider:usgs:last-success")


def test_repeated_polling_is_idempotent_including_notifications(enabled, project, django_capture_on_commit_callbacks):
    feed = usgs_feed(usgs_feature())
    with django_capture_on_commit_callbacks(execute=True):
        poll_usgs(feed)
    counts = (HazardEvent.objects.count(), ProjectSafetyAlert.objects.count(), AuditLog.objects.count(), Notification.objects.count())

    with django_capture_on_commit_callbacks(execute=True):
        outcome, _ = poll_usgs(feed, now=later(5))
        poll_usgs(feed, now=later(10))

    assert outcome.counters["events_unchanged"] == 1 and outcome.counters["alerts_created"] == 0
    assert (HazardEvent.objects.count(), ProjectSafetyAlert.objects.count(), AuditLog.objects.count(), Notification.objects.count()) == counts
    assert HazardEvent.objects.filter(provider="usgs", provider_event_id="us7000test").count() == 1
    assert Notification.objects.filter(recipient=project.manager, category="safety").count() == 1


def test_revision_updates_escalate_and_deleted_events_withdraw(enabled, project):
    poll_usgs(usgs_feed(usgs_feature(mag=5.0)))
    assert ProjectSafetyAlert.objects.get().severity == "medium"

    revised = usgs_feature(mag=6.8, updated_ms=int(later(10).timestamp() * 1000))
    outcome, _ = poll_usgs(usgs_feed(revised), now=later(10))
    alert = ProjectSafetyAlert.objects.get()
    assert outcome.counters["events_updated"] == 1 and outcome.counters["alerts_escalated"] == 1
    assert alert.severity == "critical" and HazardEvent.objects.get().revision == 2

    deleted = usgs_feature(mag=6.8, status="deleted", updated_ms=int(later(20).timestamp() * 1000))
    outcome, _ = poll_usgs(usgs_feed(deleted), now=later(20))
    alert.refresh_from_db()
    assert outcome.counters["alerts_withdrawn"] == 1
    assert alert.hazard_withdrawn_at == later(20) and alert.status == "new"
    assert HazardEvent.objects.get().provider_status == "withdrawn"


def test_malformed_records_do_not_abort_a_valid_batch(enabled, project):
    bad_coordinates = usgs_feature("us1bad", latitude=123.0)
    bad_id = usgs_feature("us2bad")
    bad_id["id"] = None
    outcome, _ = poll_usgs(usgs_feed(bad_coordinates, bad_id, usgs_feature()))
    assert outcome.status == "completed"
    assert outcome.counters["records_malformed"] == 2
    assert outcome.counters["alerts_created"] == 1


@pytest.mark.parametrize(
    "error,status,retryable",
    [
        (ProviderUnavailable("timeout"), "unavailable", True),
        (ProviderUnavailable("http_503"), "unavailable", True),
        (ProviderUnavailable("http_404", retryable=False), "unavailable", False),
        (MalformedProviderPayload("invalid_json"), "malformed", False),
    ],
)
def test_provider_failures_write_nothing_and_release_the_lock(enabled, project, error, status, retryable, caplog):
    with patch.object(usgs, "fetch_json", side_effect=error):
        outcome = polling.run_provider_poll(usgs.UsgsEarthquakeProvider(), now=NOW)
    assert (outcome.status, outcome.retryable, outcome.error_code) == (status, retryable, error.code)
    assert HazardEvent.all_objects.count() == 0 and ProjectSafetyAlert.all_objects.count() == 0
    assert cache.get(lock_key("usgs")) is None
    assert cache.get("safety:provider:usgs:last-success") is None
    assert error.code in caplog.text


def test_invalid_schema_from_provider_is_rejected(enabled, project):
    outcome, _ = poll_usgs({"type": "Feature", "features": [usgs_feature()]})
    assert (outcome.status, outcome.error_code) == ("malformed", "not_feature_collection")
    assert HazardEvent.all_objects.count() == 0


def test_rate_limit_sets_bounded_backoff_and_skips_next_poll(enabled, project):
    with patch.object(usgs, "fetch_json", side_effect=ProviderRateLimited(99999)):
        outcome = polling.run_provider_poll(usgs.UsgsEarthquakeProvider(), now=NOW)
    assert outcome.status == "rate_limited" and not outcome.retryable
    assert cache.get("safety:provider:usgs:backoff-until")

    outcome, fetch_json = poll_usgs(usgs_feed(usgs_feature()))
    assert outcome.status == "backoff"
    fetch_json.assert_not_called()


def test_overlapping_poll_is_skipped_while_locked(enabled, project):
    cache.add(lock_key("usgs"), "other-worker", timeout=60)
    outcome, fetch_json = poll_usgs(usgs_feed(usgs_feature()))
    assert outcome.status == "locked"
    fetch_json.assert_not_called()
    assert cache.get(lock_key("usgs")) == "other-worker"


def test_unexpected_errors_propagate_and_release_the_lock(enabled, project):
    with patch.object(usgs, "normalize_feed", side_effect=RuntimeError("boom")):
        with patch.object(usgs, "fetch_json", return_value={}):
            with pytest.raises(RuntimeError):
                polling.run_provider_poll(usgs.UsgsEarthquakeProvider(), now=NOW)
    assert cache.get(lock_key("usgs")) is None


def test_gdacs_earthquake_citing_usgs_does_not_duplicate_the_usgs_event(enabled, project, caplog):
    poll_usgs(usgs_feed(usgs_feature()))
    with caplog.at_level("INFO", logger="apps.safety.polling"):
        outcome, _ = poll_gdacs(
            gdacs_feed(
                gdacs_feature("EQ", 1500001, alert_level="Red", source="NEIC", source_id="us7000test"),
                gdacs_feature("FL", 1000123, alert_level="Red"),
            )
        )

    assert outcome.counters["records_reconciled"] == 1
    assert outcome.counters["records_deferred_to_usgs"] == 1
    providers = set(HazardEvent.objects.values_list("provider", "provider_event_id"))
    assert providers == {("usgs", "us7000test"), ("gdacs", "FL:1000123")}
    assert ProjectSafetyAlert.objects.filter(hazard_type="earthquake").count() == 1
    assert "gdacs_event_id=EQ:1500001 usgs_event_id=us7000test" in caplog.text


def test_uncited_gdacs_earthquake_is_not_ingested_while_usgs_is_enabled(enabled, project):
    poll_usgs(usgs_feed(usgs_feature()))
    outcome, _ = poll_gdacs(
        gdacs_feed(
            gdacs_feature(
                "EQ",
                1500002,
                alert_level="Red",
                latitude=30.3412,
                longitude=31.2357,
                source="NEIC",
                source_id="",
                severity={"severity": 6.0, "severityunit": "M"},
            )
        )
    )
    assert outcome.counters["records_deferred_to_usgs"] == 1
    assert set(HazardEvent.objects.values_list("provider", flat=True)) == {"usgs"}
    assert ProjectSafetyAlert.objects.filter(hazard_type="earthquake").count() == 1


def test_polling_never_takes_autonomous_operational_action(enabled, project, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        poll_usgs(usgs_feed(usgs_feature(mag=7.5)))
    project.refresh_from_db()
    alert = ProjectSafetyAlert.objects.get()
    assert project.status == Project.Status.IN_PROGRESS
    assert (alert.status, alert.decision, alert.decided_by_id, alert.resolved_at) == ("new", None, None, None)
    assert set(Notification.objects.values_list("category", flat=True)) == {"safety"}

    for module in (polling, tasks, usgs, gdacs):
        source = inspect.getsource(module).lower()
        for forbidden in ("notify_users", "telegram", "firebase", "channel_layer", "send_push", "decide_alert_action", "close_alert", "dismiss_alert"):
            assert forbidden not in source, (module.__name__, forbidden)


def test_ingestion_is_the_only_notification_path(enabled, project):
    with patch("apps.safety.notifications.notify_users") as notify:
        with patch.object(polling, "ingest_hazard_events", wraps=polling.ingest_hazard_events) as ingest:
            poll_usgs(usgs_feed(usgs_feature()))
    ingest.assert_called_once()
    notify.assert_not_called()  # Deferred to on_commit, which never runs here.
    assert Notification.objects.count() == 0


def test_hazard_coordinates_are_stored_as_decimals(enabled, project):
    poll_usgs(usgs_feed(usgs_feature()))
    event = HazardEvent.objects.get()
    assert event.latitude == Decimal("30.341200") and event.longitude == Decimal("31.235700")
