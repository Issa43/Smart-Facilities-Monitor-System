from unittest.mock import patch

import pytest

from apps.facilities.models import FacilityAssignment
from apps.notifications.models import Notification, NotificationPreference
from apps.projects.models import Project
from apps.safety.models import ProjectSafetyAlert
from apps.safety.services import ingest_hazard_events
from apps.safety.tests.helpers import (
    NOW,
    assign_construction_manager,
    assign_operations_manager,
    enable_alerts,
    later,
    make_facility,
    make_project,
    make_user,
    quake,
    set_setting,
)
from apps.users.models import Permission, Role, User


pytestmark = pytest.mark.django_db


@pytest.fixture
def world(settings, super_admin_user):
    enable_alerts(settings)
    facility = make_facility(super_admin_user)
    construction = make_project(super_admin_user, name="Construction site")
    operational = make_project(
        super_admin_user,
        name="Operational site",
        status=Project.Status.OPERATIONAL,
        facility=facility,
    )
    cm = make_user(Role.CONSTRUCTION_MANAGER, "cm")
    om = make_user(Role.OPERATIONS_MANAGER, "om")
    assign_construction_manager(construction, cm, super_admin_user)
    assign_operations_manager(facility, om, super_admin_user)
    return {
        "admin": super_admin_user,
        "cm": cm,
        "om": om,
        "facility": facility,
        "construction": construction,
        "operational": operational,
    }


def ingest(capture, *events, now=NOW):
    with capture(execute=True):
        return ingest_hazard_events(list(events), now=now)


def safety_notifications(user=None):
    queryset = Notification.objects.filter(category=Notification.Category.SAFETY)
    return queryset.filter(recipient=user) if user else queryset


def test_created_alert_notifies_scoped_managers_with_role_paths(world, django_capture_on_commit_callbacks):
    ingest(django_capture_on_commit_callbacks, quake(magnitude="6.0"))
    construction_alert = ProjectSafetyAlert.objects.get(project=world["construction"])
    operational_alert = ProjectSafetyAlert.objects.get(project=world["operational"])

    cm_rows = list(safety_notifications(world["cm"]))
    om_rows = list(safety_notifications(world["om"]))
    admin_rows = list(safety_notifications(world["admin"]))

    assert [row.href for row in cm_rows] == [f"/construction/safety-alerts/{construction_alert.pk}"]
    assert [row.href for row in om_rows] == [f"/operations/safety-alerts/{operational_alert.pk}"]
    assert sorted(row.href for row in admin_rows) == sorted(
        [
            f"/operations/safety-alerts/{construction_alert.pk}",
            f"/operations/safety-alerts/{operational_alert.pk}",
        ]
    )
    row = cm_rows[0]
    assert row.tone == Notification.Tone.WARNING
    assert row.source_type == "safety.projectsafetyalert"
    assert row.source_id == construction_alert.pk
    assert row.deduplication_key == f"{world['cm'].pk}:safety-alert:{construction_alert.pk}:high"
    assert "زلزال" in row.title


def test_super_admin_is_not_notified_for_medium_alerts(world, django_capture_on_commit_callbacks):
    ingest(django_capture_on_commit_callbacks, quake(magnitude="5.0"))
    assert ProjectSafetyAlert.objects.filter(severity="medium").count() == 2
    assert not safety_notifications(world["admin"]).exists()
    assert safety_notifications(world["cm"]).count() == 1


def test_ineligible_users_receive_nothing(world, django_capture_on_commit_callbacks):
    admin = world["admin"]
    no_permission_om = make_user(Role.OPERATIONS_MANAGER, "om-no-perm")
    assign_operations_manager(world["facility"], no_permission_om, admin)
    suspended_cm = make_user(Role.CONSTRUCTION_MANAGER, "cm-suspended", status=User.STATUS_SUSPENDED)
    assign_construction_manager(world["construction"], suspended_cm, admin)
    inactive_cm = make_user(Role.CONSTRUCTION_MANAGER, "cm-inactive-assignment")
    assign_construction_manager(world["construction"], inactive_cm, admin).soft_delete()
    officer = make_user(Role.SECURITY_OFFICER, "so")
    FacilityAssignment.objects.create(
        facility=world["facility"],
        user=officer,
        role_type=FacilityAssignment.RoleType.SECURITY_OFFICER,
        created_by=admin,
    )
    # Revoke after every make_user call, which re-seeds role permissions.
    Permission.objects.filter(role=no_permission_om.role, permission_name="safety.view").delete()

    ingest(django_capture_on_commit_callbacks, quake(magnitude="6.0"))

    assert not safety_notifications(world["om"]).exists()
    assert safety_notifications(world["cm"]).count() == 1
    for user in (no_permission_om, suspended_cm, inactive_cm, officer):
        assert not safety_notifications(user).exists()


def test_global_setting_and_user_preference_suppress_notifications(world, django_capture_on_commit_callbacks):
    NotificationPreference.objects.create(user=world["cm"], critical_alerts=False)
    ingest(django_capture_on_commit_callbacks, quake(event_id="first", magnitude="6.0"))
    assert not safety_notifications(world["cm"]).exists()
    assert safety_notifications(world["om"]).count() == 1

    set_setting("notify.safetyAlerts", False)
    ingest(django_capture_on_commit_callbacks, quake(event_id="second", magnitude="6.2"))
    assert safety_notifications().filter(source_id__in=ProjectSafetyAlert.objects.filter(hazard_event__provider_event_id="second").values("pk")).count() == 0
    assert ProjectSafetyAlert.objects.filter(hazard_event__provider_event_id="second").count() == 2


def test_reingestion_does_not_duplicate_notifications(world, django_capture_on_commit_callbacks):
    ingest(django_capture_on_commit_callbacks, quake(magnitude="6.0"))
    total = safety_notifications().count()
    ingest(django_capture_on_commit_callbacks, quake(magnitude="6.0"), now=later(5))
    assert safety_notifications().count() == total


def test_escalation_adds_exactly_one_notification_per_eligible_recipient(world, django_capture_on_commit_callbacks):
    ingest(django_capture_on_commit_callbacks, quake(magnitude="5.0"))
    assert safety_notifications(world["cm"]).count() == 1
    assert safety_notifications(world["admin"]).count() == 0

    ingest(django_capture_on_commit_callbacks, quake(magnitude="6.8", updated_at=later(10)), now=later(10))
    ingest(django_capture_on_commit_callbacks, quake(magnitude="6.9", updated_at=later(20)), now=later(20))

    assert safety_notifications(world["cm"]).count() == 2
    assert safety_notifications(world["om"]).count() == 2
    assert safety_notifications(world["admin"]).count() == 2
    latest = safety_notifications(world["cm"]).order_by("-created_at").first()
    assert latest.tone == Notification.Tone.CRITICAL
    assert latest.title.startswith("تصعيد")


def test_withdrawal_sends_one_informational_notification(world, django_capture_on_commit_callbacks):
    ingest(django_capture_on_commit_callbacks, quake(magnitude="6.0"))
    ingest(django_capture_on_commit_callbacks, quake(status="withdrawn", updated_at=later(10)), now=later(10))
    ingest(django_capture_on_commit_callbacks, quake(status="withdrawn", updated_at=later(20)), now=later(20))

    rows = safety_notifications(world["cm"]).order_by("created_at")
    assert rows.count() == 2
    assert rows.last().tone == Notification.Tone.INFO
    assert rows.last().deduplication_key.endswith(":withdrawn")
    assert ProjectSafetyAlert.objects.get(project=world["construction"]).status == "new"


def test_notification_failure_never_rolls_back_the_alert(world, django_capture_on_commit_callbacks, caplog):
    with patch("apps.safety.notifications.notify_users", side_effect=RuntimeError("boom")):
        result = ingest(django_capture_on_commit_callbacks, quake(magnitude="6.0"))

    assert result.alerts_created == 2
    assert ProjectSafetyAlert.objects.count() == 2
    assert all(alert.status == "new" for alert in ProjectSafetyAlert.objects.all())
    assert not safety_notifications().exists()
    assert "Safety alert notification failed" in caplog.text


def test_every_supported_hazard_type_has_an_arabic_label():
    """A hazard the domain accepts must never leak its raw code to a user.

    Regression: `dust_storm` was added to the taxonomy without an entry here,
    so notifications and Telegram rendered "رُصد dust_storm" to Arabic readers.
    """

    from apps.safety.models import HAZARD_TYPE_VALUES
    from apps.safety.notifications import HAZARD_LABELS_AR

    missing = [h for h in HAZARD_TYPE_VALUES if h not in HAZARD_LABELS_AR]
    assert missing == [], f"hazard types without an Arabic label: {missing}"
    assert all(not label.isascii() for label in HAZARD_LABELS_AR.values())


def test_every_recommendable_action_has_an_arabic_label():
    from apps.safety.models import SAFETY_ACTION_VALUES
    from apps.safety.notifications import ACTION_LABELS_AR

    missing = [a for a in SAFETY_ACTION_VALUES if a not in ACTION_LABELS_AR]
    assert missing == [], f"actions without an Arabic label: {missing}"
