"""Regression tests for the two policy gaps found by the live provider probe.

Fix 1: GDACS earthquakes are not ingested while USGS is the configured
earthquake source. Fix 2: long-running GDACS hazards are aged from their latest
provider revision, not only from their start date.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.cache import cache

from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from apps.projects.models import Project
from apps.safety import policy, polling
from apps.safety.models import HazardEvent, ProjectSafetyAlert
from apps.safety.providers import gdacs
from apps.safety.services import ingest_hazard_events
from apps.safety.tests.helpers import (
    NOW,
    assign_construction_manager,
    enable_alerts,
    make_project,
    make_user,
    quake,
)
from apps.safety.tests.provider_samples import gdacs_feature, gdacs_feed
from apps.users.models import Role


pytestmark = pytest.mark.django_db

OLD_FROM = "2026-08-20T00:00:00"
OLD_MODIFIED = "2026-08-25T00:00:00"
RECENT_MODIFIED = "2026-09-15T11:00:00"
LATER_MODIFIED = "2026-09-15T11:30:00"


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def project(settings, super_admin_user):
    enable_alerts(settings)
    site = make_project(super_admin_user)
    manager = make_user(Role.CONSTRUCTION_MANAGER, "cm")
    assign_construction_manager(site, manager, super_admin_user)
    site.manager = manager
    return site


def poll(*features, now=NOW):
    with patch.object(gdacs, "fetch_json", return_value=gdacs_feed(*features)):
        return polling.run_provider_poll(gdacs.GdacsProvider(), now=now)


def eq(event_id=1566355, **overrides):
    values = {
        "alert_level": "Red",
        "source": "NEIC",
        "source_id": "",
        "latitude": 30.3412,
        "longitude": 31.2357,
        "severity": {"severity": 6.8, "severitytext": "Magnitude 6.8M", "severityunit": "M"},
    }
    values.update(overrides)
    return gdacs_feature("EQ", event_id, **values)


# ---------------------------------------------------------------------------
# Fix 1 — GDACS earthquake source separation
# ---------------------------------------------------------------------------


def test_gdacs_earthquake_with_usgs_enabled_is_skipped_counted_and_logged(project, caplog):
    with caplog.at_level("INFO", logger="apps.safety.polling"):
        outcome = poll(eq(1566355), eq(1566315))

    assert outcome.status == "completed"
    assert outcome.counters["records_deferred_to_usgs"] == 2
    assert outcome.counters["records_normalized"] == 0
    assert outcome.counters["events_created"] == 0
    assert HazardEvent.all_objects.count() == 0
    assert "deferred to USGS provider=gdacs count=2 gdacs_event_ids=EQ:1566355,EQ:1566315" in caplog.text


def test_gdacs_earthquake_with_usgs_disabled_keeps_documented_behavior(project, settings):
    settings.SAFETY_USGS_ENABLED = False
    outcome = poll(eq())

    assert outcome.counters["records_deferred_to_usgs"] == 0
    event = HazardEvent.objects.get()
    assert (event.provider, event.provider_event_id, event.hazard_type) == ("gdacs", "EQ:1566355", "earthquake")
    assert ProjectSafetyAlert.objects.get().severity == "critical"


@pytest.mark.parametrize(
    "event_type,hazard_type",
    [("WF", "wildfire"), ("FL", "flood"), ("TC", "tropical_cyclone"), ("VO", "volcano")],
)
def test_non_earthquake_gdacs_hazards_are_still_ingested(project, event_type, hazard_type):
    outcome = poll(eq(), gdacs_feature(event_type, 1000777, alert_level="Red"))

    assert outcome.counters["records_deferred_to_usgs"] == 1
    event = HazardEvent.objects.get()
    assert (event.provider, event.provider_event_id, event.hazard_type) == ("gdacs", f"{event_type}:1000777", hazard_type)
    alert = ProjectSafetyAlert.objects.get()
    assert (alert.hazard_type, alert.severity) == (hazard_type, "critical")


def test_skipped_earthquakes_have_no_notification_audit_or_workflow_side_effects(project, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        poll(eq(1), eq(2), eq(3))
        poll(eq(1), eq(2), eq(3))

    assert HazardEvent.all_objects.count() == 0
    assert ProjectSafetyAlert.all_objects.count() == 0
    assert Notification.objects.count() == 0
    assert AuditLog.objects.filter(action__startswith="safety_alert.").count() == 0
    project.refresh_from_db()
    assert project.status == Project.Status.IN_PROGRESS


# ---------------------------------------------------------------------------
# Fix 2 — long-running GDACS hazard staleness
# ---------------------------------------------------------------------------


def flood(**overrides):
    values = {"alert_level": "Orange", "from_date": OLD_FROM, "to_date": "2026-09-30T00:00:00", "date_modified": OLD_MODIFIED}
    values.update(overrides)
    return gdacs_feature("FL", 1102030, **values)


def test_staleness_reference_uses_revision_only_for_ongoing_hazards():
    occurred = NOW - timedelta(days=20)
    updated = NOW - timedelta(hours=1)
    for hazard_type in ("tropical_cyclone", "flood", "volcano", "wildfire"):
        assert policy.staleness_reference(hazard_type=hazard_type, occurred_at=occurred, provider_updated_at=updated) == updated
    assert policy.staleness_reference(hazard_type="earthquake", occurred_at=occurred, provider_updated_at=updated) == occurred
    assert policy.staleness_reference(hazard_type="flood", occurred_at=occurred) == occurred

    rules = policy.default_policy()
    assert policy.is_stale(rules, hazard_type="flood", occurred_at=occurred, provider_updated_at=NOW - timedelta(hours=73), now=NOW)
    assert not policy.is_stale(rules, hazard_type="flood", occurred_at=occurred, provider_updated_at=updated, now=NOW)
    assert policy.is_stale(rules, hazard_type="earthquake", occurred_at=occurred, provider_updated_at=updated, now=NOW)


def test_old_unchanged_event_is_stale_and_creates_no_alert(project):
    first = poll(flood())
    again = poll(flood())

    assert first.counters["events_created"] == 1 and first.counters["alerts_created"] == 0
    assert again.counters["events_unchanged"] == 1 and again.counters["alerts_created"] == 0
    assert ProjectSafetyAlert.all_objects.count() == 0


def test_old_active_event_with_recent_revision_is_evaluated(project):
    outcome = poll(flood(date_modified=RECENT_MODIFIED))

    assert outcome.counters["alerts_created"] == 1
    alert = ProjectSafetyAlert.objects.get()
    assert (alert.hazard_type, alert.severity, alert.rule_code) == ("flood", "high", "flood.orange_r50")


def test_old_event_whose_severity_changed_recently_is_evaluated(project):
    poll(flood())
    assert ProjectSafetyAlert.all_objects.count() == 0

    outcome = poll(flood(alert_level="Red", date_modified=RECENT_MODIFIED))

    assert outcome.counters["events_updated"] == 1 and outcome.counters["alerts_created"] == 1
    event = HazardEvent.objects.get()
    assert (event.revision, event.alert_level) == (2, "red")
    assert ProjectSafetyAlert.objects.get().severity == "critical"


def test_recent_event_behavior_is_unchanged(project):
    outcome = poll(flood(from_date="2026-09-15T10:00:00", date_modified="2026-09-15T10:00:00"))
    assert outcome.counters["alerts_created"] == 1


def test_identical_revision_is_idempotent_and_notifications_stay_deduplicated(project, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        poll(flood(date_modified=RECENT_MODIFIED))
    counts = (HazardEvent.objects.count(), ProjectSafetyAlert.objects.count(), AuditLog.objects.count(), Notification.objects.count())

    with django_capture_on_commit_callbacks(execute=True):
        outcome = poll(flood(date_modified=RECENT_MODIFIED), now=NOW + timedelta(minutes=15))

    assert outcome.counters["events_unchanged"] == 1
    assert (HazardEvent.objects.count(), ProjectSafetyAlert.objects.count(), AuditLog.objects.count(), Notification.objects.count()) == counts
    assert Notification.objects.filter(recipient=project.manager, category="safety").count() == 1


def test_new_revisions_re_evaluate_without_duplicating_alerts(project, django_capture_on_commit_callbacks):
    # One capture block per poll mirrors production, where each ingestion
    # transaction commits (and delivers its notifications) before the next.
    with django_capture_on_commit_callbacks(execute=True):
        poll(flood(date_modified=RECENT_MODIFIED))
    with django_capture_on_commit_callbacks(execute=True):
        outcome = poll(flood(alert_level="Red", date_modified=LATER_MODIFIED), now=NOW + timedelta(minutes=30))
    with django_capture_on_commit_callbacks(execute=True):
        poll(flood(alert_level="Red", date_modified="2026-09-15T11:45:00"), now=NOW + timedelta(minutes=45))

    assert outcome.counters["events_updated"] == 1 and outcome.counters["alerts_escalated"] == 1
    assert HazardEvent.objects.get().revision == 3
    alert = ProjectSafetyAlert.objects.get()
    assert alert.severity == "critical"
    manager_rows = Notification.objects.filter(recipient=project.manager, category="safety")
    assert manager_rows.count() == 2  # created at "high", escalated to "critical"
    assert sorted(row.deduplication_key.rsplit(":", 1)[1] for row in manager_rows) == ["critical", "high"]


def test_provider_updates_take_no_autonomous_project_action(project, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        poll(flood(alert_level="Red", date_modified=RECENT_MODIFIED))
        poll(flood(alert_level="Red", date_modified=LATER_MODIFIED), now=NOW + timedelta(minutes=30))

    project.refresh_from_db()
    alert = ProjectSafetyAlert.objects.get()
    assert project.status == Project.Status.IN_PROGRESS
    assert (alert.status, alert.decision, alert.resolved_at) == ("new", None, None)
    human_actions = {"safety_alert.acknowledged", "safety_alert.action_decided", "safety_alert.dismissed", "safety_alert.closed"}
    assert not AuditLog.objects.filter(action__in=human_actions).exists()


def test_old_earthquake_with_recent_usgs_revision_still_creates_no_alert(project):
    old = NOW - timedelta(hours=20)
    result = ingest_hazard_events([quake(magnitude="6.8", occurred_at=old, updated_at=NOW - timedelta(minutes=5))], now=NOW)
    assert result.events_created == 1
    assert ProjectSafetyAlert.all_objects.count() == 0
