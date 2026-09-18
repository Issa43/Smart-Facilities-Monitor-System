from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from apps.audit.models import AuditLog
from apps.projects.models import Project
from apps.safety.models import HazardEvent, ProjectSafetyAlert
from apps.safety.services import (
    dismiss_alert,
    ingest_hazard_events,
    monitoring_coverage,
)
from apps.safety.tests.helpers import (
    CAIRO,
    NOW,
    enable_alerts,
    later,
    make_project,
    offset_north,
    quake,
    set_setting,
)


pytestmark = pytest.mark.django_db


@pytest.fixture
def project(super_admin_user):
    return make_project(super_admin_user)


@pytest.fixture
def enabled(settings):
    enable_alerts(settings)


def test_nothing_is_written_while_kill_switches_are_off(settings, project):
    settings.SAFETY_ALERTS_ENABLED = False
    set_setting("safety.externalAlerts", True)
    result = ingest_hazard_events([quake()], now=NOW)
    assert result.enabled is False
    assert HazardEvent.all_objects.count() == 0

    settings.SAFETY_ALERTS_ENABLED = True
    set_setting("safety.externalAlerts", False)
    result = ingest_hazard_events([quake()], now=NOW)
    assert result.enabled is False
    assert HazardEvent.all_objects.count() == 0
    assert ProjectSafetyAlert.all_objects.count() == 0


def test_ingestion_creates_event_and_snapshotted_alert(enabled, project):
    result = ingest_hazard_events([quake(magnitude="6.0", distance_km=33)], now=NOW)

    assert (result.events_created, result.alerts_created) == (1, 1)
    event = HazardEvent.objects.get()
    assert event.revision == 1 and event.last_seen_at == NOW
    assert event.payload == {"mag": "6.0", "place": "synthetic"}
    alert = ProjectSafetyAlert.objects.get()
    assert alert.project_id == project.pk
    assert alert.status == "new"
    assert alert.severity == "high"
    assert alert.rule_code == "earthquake.m5_5_r100"
    assert alert.recommended_action == "suspend_outdoor_work"
    assert alert.policy_version == 0
    assert (alert.project_latitude, alert.project_longitude) == CAIRO
    assert Decimal("32.5") < alert.distance_km < Decimal("33.5")

    audit = AuditLog.objects.get(action="safety_alert.created")
    assert audit.actor_id is None
    assert audit.entity_id == str(alert.pk)
    assert audit.after["severity"] == "high"
    assert "payload" not in audit.after and "synthetic" not in str(audit.after)


def test_unmonitored_missing_coordinate_and_distant_projects_get_no_alert(enabled, super_admin_user):
    make_project(super_admin_user, name="Planning", status=Project.Status.PLANNING)
    make_project(super_admin_user, name="No coordinates", latitude=None, longitude=None)
    make_project(super_admin_user, name="Completed", status=Project.Status.COMPLETED)
    make_project(super_admin_user, name="Distant", latitude=Decimal("40.0"))

    result = ingest_hazard_events([quake()], now=NOW)

    assert result.events_ignored == 1
    assert HazardEvent.all_objects.count() == 0
    assert ProjectSafetyAlert.all_objects.count() == 0
    # "No coordinates" is in progress, so it is monitored but cannot match.
    assert monitoring_coverage() == {
        "monitored_projects": 2,
        "projects_with_coordinates": 1,
        "projects_missing_coordinates": 1,
    }


def test_coverage_counts_missing_coordinates(super_admin_user):
    make_project(super_admin_user, name="A")
    make_project(super_admin_user, name="B", latitude=None, longitude=None)
    make_project(super_admin_user, name="Planning", latitude=None, longitude=None, status=Project.Status.PLANNING)
    assert monitoring_coverage()["projects_missing_coordinates"] == 1


def test_reingesting_identical_event_is_idempotent(enabled, project):
    ingest_hazard_events([quake()], now=NOW)
    audits = AuditLog.objects.count()

    result = ingest_hazard_events([quake()], now=later(5))

    assert result.events_unchanged == 1 and result.alerts_created == 0
    assert HazardEvent.objects.get().last_seen_at == later(5)
    assert ProjectSafetyAlert.objects.count() == 1
    assert AuditLog.objects.count() == audits


def test_older_provider_update_never_overwrites_newer_state(enabled, project):
    ingest_hazard_events([quake(magnitude="6.0")], now=NOW)
    ingest_hazard_events([quake(magnitude="6.1", updated_at=later(10))], now=later(10))

    result = ingest_hazard_events([quake(magnitude="5.9", updated_at=later(5))], now=later(15))

    assert result.stale_updates_ignored == 1
    event = HazardEvent.objects.get()
    assert event.magnitude == Decimal("6.10")
    assert event.revision == 2
    assert event.provider_updated_at == later(10)


def test_escalation_updates_severity_once_and_downgrade_is_ignored(enabled, project):
    ingest_hazard_events([quake(magnitude="5.0", distance_km=33)], now=NOW)
    alert = ProjectSafetyAlert.objects.get()
    assert alert.severity == "medium"

    result = ingest_hazard_events([quake(magnitude="6.8", updated_at=later(10))], now=later(10))
    alert.refresh_from_db()
    assert result.alerts_escalated == 1
    assert alert.severity == "critical"
    assert alert.escalated_at == later(10)
    assert alert.rule_code == "earthquake.m6_5_r250"
    assert AuditLog.objects.filter(action="safety_alert.escalated").count() == 1

    result = ingest_hazard_events([quake(magnitude="5.0", updated_at=later(20))], now=later(20))
    alert.refresh_from_db()
    assert result.alerts_escalated == 0
    assert alert.severity == "critical"
    assert ProjectSafetyAlert.objects.count() == 1


def test_resolved_alerts_are_not_escalated(enabled, project, super_admin_user):
    ingest_hazard_events([quake(magnitude="5.0")], now=NOW)
    alert = ProjectSafetyAlert.objects.get()
    dismiss_alert(alert_id=alert.pk, actor=super_admin_user, reason="Outside working hours.")

    ingest_hazard_events([quake(magnitude="7.0", updated_at=later(10))], now=later(10))

    alert.refresh_from_db()
    assert (alert.status, alert.severity) == ("dismissed", "medium")


def test_withdrawal_flags_open_alerts_without_closing_them(enabled, project):
    ingest_hazard_events([quake()], now=NOW)

    result = ingest_hazard_events([quake(status="withdrawn", updated_at=later(10))], now=later(10))
    alert = ProjectSafetyAlert.objects.get()
    assert result.alerts_withdrawn == 1
    assert alert.status == "new"
    assert alert.hazard_withdrawn_at == later(10)
    assert AuditLog.objects.filter(action="safety_alert.hazard_withdrawn").count() == 1

    ingest_hazard_events([quake(status="withdrawn", updated_at=later(20))], now=later(20))
    assert AuditLog.objects.filter(action="safety_alert.hazard_withdrawn").count() == 1
    assert ProjectSafetyAlert.objects.get().status == "new"


def test_never_seen_withdrawn_event_creates_nothing(enabled, project):
    result = ingest_hazard_events([quake(status="withdrawn")], now=NOW)
    assert result.events_ignored == 1
    assert HazardEvent.all_objects.count() == 0


def test_stale_event_is_recorded_but_creates_no_alert(enabled, project):
    result = ingest_hazard_events([quake(occurred_at=NOW - timedelta(hours=7))], now=NOW)
    assert result.events_created == 1
    assert ProjectSafetyAlert.all_objects.count() == 0


def test_revision_alerts_newly_monitored_project(enabled, project, super_admin_user):
    ingest_hazard_events([quake()], now=NOW)
    second = make_project(super_admin_user, name="New site", latitude=offset_north(CAIRO[0], 20))

    result = ingest_hazard_events([quake(updated_at=later(5))], now=later(5))

    assert result.alerts_created == 1
    assert set(ProjectSafetyAlert.objects.values_list("project_id", flat=True)) == {project.pk, second.pk}


def test_project_coordinate_edits_do_not_rewrite_alert_history(enabled, project):
    ingest_hazard_events([quake(magnitude="5.0")], now=NOW)
    alert = ProjectSafetyAlert.objects.get()
    original_distance = alert.distance_km

    Project.objects.filter(pk=project.pk).update(latitude=Decimal("10.0"))
    ingest_hazard_events([quake(magnitude="6.8", updated_at=later(10))], now=later(10))

    alert.refresh_from_db()
    assert (alert.project_latitude, alert.project_longitude) == CAIRO
    assert alert.severity == "critical"
    assert alert.distance_km == original_distance


def test_invalid_event_is_skipped_without_blocking_valid_events(enabled, project):
    naive = quake(event_id="bad-time", occurred_at=datetime(2026, 9, 15, 12, 0))
    bad_url = quake(event_id="bad-url", source_url="https://evil.example/x")
    bad_type = replace(quake(event_id="bad-type"), hazard_type="tsunami")
    bad_coords = quake(event_id="bad-coords", latitude=Decimal("123"))

    result = ingest_hazard_events([naive, bad_url, bad_type, bad_coords, quake(event_id="good")], now=NOW)

    assert result.invalid_skipped == 4
    assert result.alerts_created == 1
    assert list(HazardEvent.objects.values_list("provider_event_id", flat=True)) == ["good"]


def test_unsupported_contract_is_skipped(enabled, project):
    result = ingest_hazard_events([{"provider": "usgs"}], now=NOW)
    assert result.invalid_skipped == 1
    assert HazardEvent.all_objects.count() == 0
