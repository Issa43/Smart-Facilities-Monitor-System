import inspect

import pytest

from api.v1.safety import views
from api.v1.safety.tests.world import build_world
from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from apps.projects.models import Project
from apps.safety.models import ProjectSafetyAlert
from apps.safety.services import ingest_hazard_events
from apps.safety.tests.helpers import later, quake
from apps.users.models import Permission, User


pytestmark = pytest.mark.django_db

ALERTS = "/api/v1/safety/alerts/"


@pytest.fixture
def world(settings, super_admin_user):
    return build_world(settings, super_admin_user)


def post(api_client, user, alert, action, data=None):
    api_client.force_authenticate(user)
    return api_client.post(f"{ALERTS}{alert.pk}/{action}/", data or {}, format="json")


def semantic_actions(alert):
    return list(
        AuditLog.objects.filter(entity_id=str(alert.pk), action__startswith="safety_alert.")
        .exclude(action="safety_alert.created")
        .order_by("created_at", "id")
        .values_list("action", flat=True)
    )


def refreshed(alert):
    return ProjectSafetyAlert.objects.get(pk=alert.pk)


def test_full_lifecycle_through_the_api_reuses_domain_audit_without_notifications(api_client, world):
    alert = world.alert_construction
    notifications_before = Notification.objects.count()

    response = post(api_client, world.cm_cairo, alert, "acknowledge")
    assert response.status_code == 200
    assert response.data["status"] == "acknowledged"
    assert response.json()["acknowledged_by"] == {"id": str(world.cm_cairo.pk), "full_name": world.cm_cairo.full_name}
    assert response.data["available_actions"] == ["decide", "dismiss"]

    # Recording a decision reaches people, so it needs the General Manager.
    assert post(api_client, world.cm_cairo, alert, "decide", {"decision": "suspend_outdoor_work"}).status_code == 403
    response = post(api_client, world.admin, alert, "decide", {"decision": "suspend_outdoor_work", "notes": "Stop crane lifts."})
    assert response.status_code == 200
    assert (response.data["status"], response.data["decision"]) == ("actioned", "suspend_outdoor_work")
    assert response.data["available_actions"] == ["decide", "close"]

    response = post(api_client, world.cm_cairo, alert, "close", {"notes": "Inspection passed."})
    assert response.status_code == 200
    assert response.data["status"] == "closed" and response.data["available_actions"] == []
    assert response.json()["resolved_by"]["id"] == str(world.cm_cairo.pk)

    assert semantic_actions(alert) == ["safety_alert.acknowledged", "safety_alert.action_decided", "safety_alert.closed"]
    assert Notification.objects.count() == notifications_before
    source = inspect.getsource(views)
    assert "notify_users" not in source and "record_audit" not in source


def test_acknowledge_repeat_is_idempotent_for_same_user_and_conflicts_for_others(api_client, world):
    alert = world.alert_operational_cairo
    assert post(api_client, world.om_cairo, alert, "acknowledge").status_code == 200
    assert post(api_client, world.om_cairo, alert, "acknowledge").status_code == 200
    assert semantic_actions(alert) == ["safety_alert.acknowledged"]

    response = post(api_client, world.admin, alert, "acknowledge")
    assert response.status_code == 409
    assert response.data["success"] is False and response.data["error"]["code"] == 409


def test_decide_transition_rules_and_validation(api_client, world):
    """Validation is unchanged; the authority to decide is the General Manager's."""

    alert = world.alert_tokyo_quake
    assert post(api_client, world.admin, alert, "decide", {"decision": "monitor"}).status_code == 409
    post(api_client, world.om_tokyo, alert, "acknowledge")

    # A manager in scope still cannot record the decision itself.
    assert post(api_client, world.om_tokyo, alert, "decide", {"decision": "monitor"}).status_code == 403
    assert post(api_client, world.cm_tokyo, alert, "decide", {"decision": "delay_shift"}).status_code == 403

    assert post(api_client, world.admin, alert, "decide", {"decision": "evacuate"}).status_code == 400
    assert post(api_client, world.admin, alert, "decide", {}).status_code == 400
    assert post(api_client, world.admin, alert, "decide", {"decision": "monitor", "notes": "x" * 2001}).status_code == 400
    assert post(api_client, world.admin, alert, "decide", {"decision": "other"}).status_code == 409
    assert refreshed(alert).status == "acknowledged"

    assert post(api_client, world.admin, alert, "decide", {"decision": "other", "notes": "Delay concrete pour."}).status_code == 200
    assert post(api_client, world.admin, alert, "decide", {"decision": "delay_shift"}).status_code == 200
    assert semantic_actions(alert) == ["safety_alert.acknowledged", "safety_alert.action_decided", "safety_alert.action_decided"]
    assert (refreshed(alert).decision, refreshed(alert).decided_by_id) == ("delay_shift", world.admin.pk)


def test_dismiss_rules(api_client, world):
    alert = world.alert_tokyo_flood
    assert post(api_client, world.cm_tokyo, alert, "dismiss", {}).status_code == 400
    assert post(api_client, world.cm_tokyo, alert, "dismiss", {"reason": ""}).status_code == 400
    response = post(api_client, world.cm_tokyo, alert, "dismiss", {"reason": "River gauge below threshold."})
    assert response.status_code == 200 and response.data["status"] == "dismissed"
    assert post(api_client, world.cm_tokyo, alert, "acknowledge").status_code == 409

    actioned = world.alert_tokyo_quake
    post(api_client, world.om_tokyo, actioned, "acknowledge")
    post(api_client, world.admin, actioned, "decide", {"decision": "monitor"})
    assert post(api_client, world.om_tokyo, actioned, "dismiss", {"reason": "Too late"}).status_code == 409
    assert refreshed(actioned).status == "actioned"


def test_close_rules_and_closed_alerts_are_final(api_client, world):
    alert = world.alert_construction
    assert post(api_client, world.admin, alert, "close").status_code == 409
    post(api_client, world.admin, alert, "acknowledge")
    assert post(api_client, world.admin, alert, "close").status_code == 409
    post(api_client, world.admin, alert, "decide", {"decision": "inspect_site"})
    assert post(api_client, world.admin, alert, "close", {}).status_code == 200
    for action, data in [("acknowledge", {}), ("decide", {"decision": "monitor"}), ("dismiss", {"reason": "x"}), ("close", {})]:
        assert post(api_client, world.admin, alert, action, data).status_code == 409
    assert refreshed(alert).status == "closed"


@pytest.mark.parametrize(
    "action,data",
    [
        ("acknowledge", {"status": "closed"}),
        ("decide", {"decision": "monitor", "severity": "low"}),
        ("decide", {"decision": "monitor", "project": "00000000-0000-0000-0000-000000000000"}),
        ("decide", {"decision": "monitor", "decided_by": 1, "recommended_action": "monitor"}),
        ("dismiss", {"reason": "x", "hazard_event": "x", "provider": "gdacs"}),
        ("close", {"notes": "x", "distance_km": "0", "created_at": "2000-01-01T00:00:00Z"}),
    ],
)
def test_server_owned_and_unknown_fields_are_rejected(api_client, world, action, data):
    alert = world.alert_construction
    before = ProjectSafetyAlert.objects.filter(pk=alert.pk).values().get()
    response = post(api_client, world.cm_cairo, alert, action, data)
    assert response.status_code == 400
    assert ProjectSafetyAlert.objects.filter(pk=alert.pk).values().get() == before


def test_non_object_payload_is_rejected(api_client, world):
    api_client.force_authenticate(world.cm_cairo)
    for payload in (["x"], "text", 42):
        response = api_client.post(f"{ALERTS}{world.alert_construction.pk}/acknowledge/", payload, format="json")
        assert response.status_code == 400
        assert response.json()["success"] is False
    assert refreshed(world.alert_construction).status == "new"


def test_missing_manage_permission_is_forbidden_and_changes_nothing(api_client, world):
    Permission.objects.filter(role=world.cm_cairo.role, permission_name="safety.manage").delete()
    alert = world.alert_construction
    for action, data in [("acknowledge", {}), ("decide", {"decision": "monitor"}), ("dismiss", {"reason": "x"}), ("close", {})]:
        assert post(api_client, world.cm_cairo, alert, action, data).status_code == 403
    assert refreshed(alert).status == "new" and semantic_actions(alert) == []


@pytest.mark.parametrize(
    "user_attr,alert_attr",
    [("cm_cairo", "alert_operational_cairo"), ("om_cairo", "alert_construction"), ("cm_tokyo", "alert_construction")],
)
def test_out_of_scope_actions_are_not_found_and_change_nothing(api_client, world, user_attr, alert_attr):
    alert = getattr(world, alert_attr)
    for action, data in [("acknowledge", {}), ("decide", {"decision": "monitor"}), ("dismiss", {"reason": "x"}), ("close", {})]:
        assert post(api_client, getattr(world, user_attr), alert, action, data).status_code == 404
    assert refreshed(alert).status == "new" and semantic_actions(alert) == []


def test_inactive_security_officer_and_roleless_users_cannot_act(api_client, world):
    alert = world.alert_operational_cairo
    assert post(api_client, world.officer, alert, "acknowledge").status_code == 403
    principal = User.objects.create_user(email="machine@sflms.test", username="machine", full_name="Machine", password=None)
    assert post(api_client, principal, alert, "acknowledge").status_code == 403
    User.objects.filter(pk=world.om_cairo.pk).update(status=User.STATUS_SUSPENDED)
    world.om_cairo.refresh_from_db()
    assert post(api_client, world.om_cairo, alert, "acknowledge").status_code == 403
    api_client.force_authenticate(None)
    assert api_client.post(f"{ALERTS}{alert.pk}/acknowledge/", {}, format="json").status_code == 401
    assert refreshed(alert).status == "new"


def test_withdrawn_alerts_remain_actionable_as_the_domain_permits(api_client, world):
    ingest_hazard_events(
        [quake(event_id="us-cairo", magnitude="6.0", distance_km=33, status="withdrawn", updated_at=later(10))],
        now=later(10),
    )
    alert = world.alert_construction
    detail = post(api_client, world.cm_cairo, alert, "acknowledge")
    assert detail.status_code == 200
    assert detail.data["hazard_withdrawn_at"] is not None and detail.data["status"] == "acknowledged"
    api_client.force_authenticate(world.cm_cairo)
    assert api_client.get(ALERTS, {"hazard_withdrawn": "true"}).data["count"] == 1


def test_workflow_actions_never_change_project_state(api_client, world):
    alert = world.alert_construction
    post(api_client, world.cm_cairo, alert, "acknowledge")
    post(api_client, world.cm_cairo, alert, "decide", {"decision": "suspend_outdoor_work"})
    world.construction.refresh_from_db()
    assert world.construction.status == Project.Status.IN_PROGRESS
