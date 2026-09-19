import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.audit.models import AuditLog
from apps.facilities.models import FacilityAssignment
from apps.projects.models import Project, ProjectAssignment
from apps.safety.models import ProjectSafetyAlert
from apps.safety.recipients import user_can_manage_alert, user_can_view_alert
from apps.safety.services import (
    acknowledge_alert,
    available_actions,
    close_alert,
    decide_alert_action,
    dismiss_alert,
    ingest_hazard_events,
)
from apps.safety.tests.helpers import (
    NOW,
    assign_construction_manager,
    assign_operations_manager,
    enable_alerts,
    make_facility,
    make_project,
    make_user,
    quake,
)
from apps.users.models import Permission, Role, User


pytestmark = pytest.mark.django_db


@pytest.fixture
def world(settings, super_admin_user):
    enable_alerts(settings)
    cm = make_user(Role.CONSTRUCTION_MANAGER, "cm")
    facility = make_facility(super_admin_user)
    om = make_user(Role.OPERATIONS_MANAGER, "om")
    construction = make_project(super_admin_user, name="Construction site")
    operational = make_project(
        super_admin_user,
        name="Operational site",
        status=Project.Status.OPERATIONAL,
        facility=facility,
    )
    assign_construction_manager(construction, cm, super_admin_user)
    assign_operations_manager(facility, om, super_admin_user)
    ingest_hazard_events([quake(magnitude="6.0")], now=NOW)
    return {
        "admin": super_admin_user,
        "cm": cm,
        "om": om,
        "facility": facility,
        "construction_alert": ProjectSafetyAlert.objects.get(project=construction),
        "operational_alert": ProjectSafetyAlert.objects.get(project=operational),
    }


def test_full_lifecycle_with_server_calculated_actions(world):
    """Triage by the responsible manager, the ruling by the General Manager.

    Recording a decision is what reaches people, so it is the General
    Manager's to make; acknowledging and closing stay with the manager
    responsible for the site.
    """

    alert = world["construction_alert"]
    cm = world["cm"]
    admin = world["admin"]
    assert available_actions(alert) == ["acknowledge", "dismiss"]

    alert = acknowledge_alert(alert_id=alert.pk, actor=cm)
    assert (alert.status, alert.acknowledged_by_id) == ("acknowledged", cm.pk)
    assert available_actions(alert) == ["decide", "dismiss"]

    with pytest.raises(PermissionDenied):
        decide_alert_action(alert_id=alert.pk, actor=cm, decision="suspend_outdoor_work", notes="Stop crane work.")

    alert = decide_alert_action(alert_id=alert.pk, actor=admin, decision="suspend_outdoor_work", notes="Stop crane work.")
    assert (alert.status, alert.decision, alert.decided_by_id) == ("actioned", "suspend_outdoor_work", admin.pk)
    assert available_actions(alert) == ["decide", "close"]

    alert = close_alert(alert_id=alert.pk, actor=cm, notes="Site inspected, resumed.")
    assert alert.status == "closed" and alert.resolved_by_id == cm.pk
    assert available_actions(alert) == []

    actions = list(
        AuditLog.objects.filter(entity_id=str(alert.pk))
        .exclude(action="safety_alert.created")
        .order_by("created_at", "id")
        .values_list("action", flat=True)
    )
    assert actions == ["safety_alert.acknowledged", "safety_alert.action_decided", "safety_alert.closed"]
    decided = AuditLog.objects.get(action="safety_alert.action_decided")
    assert decided.before["status"] == "acknowledged"
    assert decided.after["decision_notes_length"] == len("Stop crane work.")
    assert "Stop crane work." not in str(decided.after)


def test_dismissal_paths_and_reason_requirement(world):
    admin = world["admin"]
    first = world["construction_alert"]
    with pytest.raises(ValidationError):
        dismiss_alert(alert_id=first.pk, actor=admin, reason="   ")
    first = dismiss_alert(alert_id=first.pk, actor=admin, reason="False report")
    assert first.status == "dismissed" and first.resolution_notes == "False report"

    second = world["operational_alert"]
    acknowledge_alert(alert_id=second.pk, actor=admin)
    assert dismiss_alert(alert_id=second.pk, actor=admin, reason="Not applicable").status == "dismissed"


def test_illegal_transitions_raise_validation_errors(world):
    admin = world["admin"]
    alert = world["construction_alert"]
    with pytest.raises(ValidationError):
        close_alert(alert_id=alert.pk, actor=admin)
    with pytest.raises(ValidationError):
        decide_alert_action(alert_id=alert.pk, actor=admin, decision="monitor")

    acknowledge_alert(alert_id=alert.pk, actor=admin)
    decide_alert_action(alert_id=alert.pk, actor=admin, decision="monitor")
    with pytest.raises(ValidationError):
        acknowledge_alert(alert_id=alert.pk, actor=admin)
    with pytest.raises(ValidationError):
        dismiss_alert(alert_id=alert.pk, actor=admin, reason="Too late")

    close_alert(alert_id=alert.pk, actor=admin)
    with pytest.raises(ValidationError):
        decide_alert_action(alert_id=alert.pk, actor=admin, decision="delay_shift")
    assert ProjectSafetyAlert.objects.get(pk=alert.pk).status == "closed"


def test_acknowledge_is_idempotent_for_same_user_only(world):
    alert = world["construction_alert"]
    acknowledge_alert(alert_id=alert.pk, actor=world["cm"])
    count = AuditLog.objects.filter(action="safety_alert.acknowledged").count()

    acknowledge_alert(alert_id=alert.pk, actor=world["cm"])
    assert AuditLog.objects.filter(action="safety_alert.acknowledged").count() == count
    with pytest.raises(ValidationError):
        acknowledge_alert(alert_id=alert.pk, actor=world["admin"])


def test_decision_validation_and_audited_revision(world):
    admin = world["admin"]
    alert = world["construction_alert"]
    acknowledge_alert(alert_id=alert.pk, actor=admin)
    with pytest.raises(ValidationError):
        decide_alert_action(alert_id=alert.pk, actor=admin, decision="evacuate")
    with pytest.raises(ValidationError):
        decide_alert_action(alert_id=alert.pk, actor=admin, decision="other", notes=" ")
    with pytest.raises(ValidationError):
        decide_alert_action(alert_id=alert.pk, actor=admin, decision="monitor", notes="x" * 2001)
    with pytest.raises(ValidationError):
        decide_alert_action(alert_id=alert.pk, actor=admin, decision="monitor", notes="bad\x00note")

    decide_alert_action(alert_id=alert.pk, actor=admin, decision="other", notes="Hold pour.")
    decide_alert_action(alert_id=alert.pk, actor=admin, decision="other", notes="Hold pour.")
    decide_alert_action(alert_id=alert.pk, actor=admin, decision="delay_shift")
    assert AuditLog.objects.filter(action="safety_alert.action_decided").count() == 2
    alert.refresh_from_db()
    assert (alert.decision, alert.decision_notes) == ("delay_shift", "")


def test_scope_is_enforced_for_every_role(world):
    cm, om = world["cm"], world["om"]
    construction, operational = world["construction_alert"], world["operational_alert"]
    other_cm = make_user(Role.CONSTRUCTION_MANAGER, "other-cm")
    officer = make_user(Role.SECURITY_OFFICER, "so")
    FacilityAssignment.objects.create(
        facility=world["facility"],
        user=officer,
        role_type=FacilityAssignment.RoleType.SECURITY_OFFICER,
        created_by=world["admin"],
    )

    assert user_can_manage_alert(cm, construction) and not user_can_manage_alert(cm, operational)
    assert user_can_manage_alert(om, operational) and not user_can_manage_alert(om, construction)
    assert not user_can_view_alert(officer, operational)
    for actor, alert in [(other_cm, construction), (cm, operational), (om, construction), (officer, operational)]:
        with pytest.raises(PermissionDenied):
            acknowledge_alert(alert_id=alert.pk, actor=actor)
    assert acknowledge_alert(alert_id=operational.pk, actor=om).status == "acknowledged"


def test_missing_permission_inactive_assignment_and_suspended_user_are_denied(world):
    cm = world["cm"]
    alert = world["construction_alert"]
    Permission.objects.filter(role=cm.role, permission_name="safety.manage").delete()
    assert user_can_view_alert(cm, alert) and not user_can_manage_alert(cm, alert)
    with pytest.raises(PermissionDenied):
        acknowledge_alert(alert_id=alert.pk, actor=cm)

    Permission.objects.get_or_create(role=cm.role, permission_name="safety.manage")
    ProjectAssignment.objects.filter(user=cm).update(is_active=False)
    with pytest.raises(PermissionDenied):
        acknowledge_alert(alert_id=alert.pk, actor=cm)

    ProjectAssignment.objects.filter(user=cm).update(is_active=True)
    User.objects.filter(pk=cm.pk).update(status=User.STATUS_SUSPENDED)
    cm.refresh_from_db()
    with pytest.raises(ValidationError):
        acknowledge_alert(alert_id=alert.pk, actor=cm)


def test_inactive_facility_removes_operations_scope(world):
    world["facility"].soft_delete()
    with pytest.raises(PermissionDenied):
        acknowledge_alert(alert_id=world["operational_alert"].pk, actor=world["om"])
