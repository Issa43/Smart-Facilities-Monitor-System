import uuid

import pytest
from rest_framework_simplejwt.tokens import AccessToken

from api.v1.safety.tests.world import PAYLOAD_MARKER, build_world
from apps.safety.tests.helpers import make_user, set_setting
from apps.users.models import Permission, Role, User


pytestmark = pytest.mark.django_db

ALERTS = "/api/v1/safety/alerts/"
EVENTS = "/api/v1/safety/hazard-events/"
COVERAGE = "/api/v1/safety/monitoring-coverage/"


@pytest.fixture
def world(settings, super_admin_user):
    return build_world(settings, super_admin_user)


def as_user(api_client, user):
    api_client.force_authenticate(user)
    return api_client


def ids(response):
    return {item["id"] for item in response.data["results"]}


# --- Authentication and RBAC -------------------------------------------------


@pytest.mark.parametrize("path", [ALERTS, EVENTS, COVERAGE])
def test_anonymous_requests_are_rejected(api_client, world, path):
    response = api_client.get(path)
    assert response.status_code == 401
    assert response.data["success"] is False


@pytest.mark.parametrize("header", ["AIKey aic_example:secret", "Bearer not-a-jwt"])
def test_machine_or_invalid_credentials_are_rejected(api_client, world, header):
    response = api_client.get(ALERTS, HTTP_AUTHORIZATION=header)
    assert response.status_code == 401


def test_real_jwt_authentication_and_inactive_token(api_client, world):
    token = str(AccessToken.for_user(world.cm_cairo))
    response = api_client.get(ALERTS, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200 and response.data["count"] == 1

    User.objects.filter(pk=world.cm_cairo.pk).update(status=User.STATUS_SUSPENDED)
    response = api_client.get(ALERTS, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code in (401, 403)
    assert response.data["success"] is False


def test_roleless_machine_principal_is_forbidden(api_client, world):
    principal = User.objects.create_user(email="machine@sflms.test", username="machine", full_name="Machine", password=None)
    assert as_user(api_client, principal).get(ALERTS).status_code == 403


def test_inactive_manager_is_forbidden(api_client, world):
    User.objects.filter(pk=world.cm_cairo.pk).update(status=User.STATUS_SUSPENDED)
    world.cm_cairo.refresh_from_db()
    assert as_user(api_client, world.cm_cairo).get(ALERTS).status_code == 403


@pytest.mark.parametrize("path", [ALERTS, EVENTS, COVERAGE])
def test_security_officer_is_forbidden_even_with_safety_permission(api_client, world, path):
    Permission.objects.get_or_create(role=world.officer.role, permission_name="safety.view")
    response = as_user(api_client, world.officer).get(path)
    assert response.status_code == 403
    assert response.data["error"]["code"] == 403


def test_manager_without_safety_view_is_forbidden(api_client, world):
    Permission.objects.filter(role=world.cm_cairo.role, permission_name="safety.view").delete()
    assert as_user(api_client, world.cm_cairo).get(ALERTS).status_code == 403


# --- Alert scoping -----------------------------------------------------------


def test_alert_lists_are_scoped_per_role(api_client, world):
    expected = {
        world.cm_cairo: {world.alert_construction.pk},
        world.cm_tokyo: {world.alert_tokyo_quake.pk, world.alert_tokyo_flood.pk},
        world.om_cairo: {world.alert_operational_cairo.pk},
        world.om_tokyo: {world.alert_tokyo_quake.pk, world.alert_tokyo_flood.pk},
        world.admin: {
            world.alert_construction.pk,
            world.alert_operational_cairo.pk,
            world.alert_tokyo_quake.pk,
            world.alert_tokyo_flood.pk,
        },
    }
    for user, alert_ids in expected.items():
        response = as_user(api_client, user).get(ALERTS)
        assert response.status_code == 200
        assert ids(response) == {str(pk) for pk in alert_ids}, user.username


@pytest.mark.parametrize(
    "user_attr,alert_attr",
    [
        ("cm_cairo", "alert_operational_cairo"),
        ("cm_cairo", "alert_tokyo_quake"),
        ("om_cairo", "alert_construction"),
        ("om_cairo", "alert_tokyo_flood"),
        ("om_tokyo", "alert_operational_cairo"),
    ],
)
def test_out_of_scope_alert_detail_is_not_found(api_client, world, user_attr, alert_attr):
    alert = getattr(world, alert_attr)
    response = as_user(api_client, getattr(world, user_attr)).get(f"{ALERTS}{alert.pk}/")
    assert response.status_code == 404


def test_query_parameters_cannot_widen_scope(api_client, world):
    client = as_user(api_client, world.cm_cairo)
    assert client.get(ALERTS, {"project": str(world.operational_tokyo.pk)}).data["count"] == 0
    assert client.get(ALERTS, {"project": str(world.construction.pk)}).data["count"] == 1
    assert client.get(ALERTS, {"provider": "gdacs"}).data["count"] == 0
    assert client.get(EVENTS, {"project": str(world.operational_tokyo.pk)}).data["count"] == 0


def test_assignment_removal_revokes_access_immediately(api_client, world):
    world.cm_cairo.project_assignments.update(is_active=False)
    client = as_user(api_client, world.cm_cairo)
    assert client.get(ALERTS).data["count"] == 0
    assert client.get(f"{ALERTS}{world.alert_construction.pk}/").status_code == 404
    world.facility_cairo.soft_delete()
    assert as_user(api_client, world.om_cairo).get(ALERTS).data["count"] == 0


def test_unknown_or_malformed_alert_ids_are_not_found(api_client, world):
    client = as_user(api_client, world.admin)
    assert client.get(f"{ALERTS}{uuid.uuid4()}/").status_code == 404
    assert client.get(f"{ALERTS}not-a-uuid/").status_code == 404


# --- Alert contract ------------------------------------------------------------


def test_alert_detail_contract_is_explicit_and_leaks_no_payload(api_client, world):
    response = as_user(api_client, world.cm_tokyo).get(f"{ALERTS}{world.alert_tokyo_quake.pk}/")

    assert response.status_code == 200
    body = response.data
    assert set(body) == {
        "id", "project", "hazard_event", "hazard_type", "severity", "status", "distance_km",
        "project_latitude", "project_longitude", "rule_code", "policy_version",
        "recommended_action", "decision", "decision_notes", "acknowledged_by",
        "acknowledged_at", "decided_by", "decided_at", "resolution_notes", "resolved_by",
        "resolved_at", "hazard_withdrawn_at", "escalated_at", "available_actions",
        # The human decision workflow, both server-calculated for this viewer.
        "available_proposal_types", "open_proposals",
        "created_at", "updated_at",
    }
    assert set(body["project"]) == {"id", "name", "location", "status", "facility_id"}
    assert set(body["hazard_event"]) == {
        "id", "provider", "provider_event_id", "hazard_type", "title", "alert_level",
        "provider_severity", "magnitude", "depth_km", "latitude", "longitude", "radius_km",
        "occurred_at", "valid_from", "valid_until", "provider_updated_at", "provider_status",
        "revision", "source_url", "created_at", "updated_at",
    }
    assert (body["severity"], body["status"], body["recommended_action"]) == ("critical", "new", "suspend_outdoor_work")
    assert body["hazard_event"]["provider"] == "usgs"
    assert body["project_latitude"] == "35.676200"
    assert body["available_actions"] == ["acknowledge", "dismiss"]
    assert body["acknowledged_by"] is None and body["decision"] is None
    assert PAYLOAD_MARKER not in response.content.decode()
    assert "secret-token" not in response.content.decode()
    assert "payload" not in response.content.decode()


def test_available_actions_are_empty_without_manage_permission(api_client, world):
    Permission.objects.filter(role=world.om_tokyo.role, permission_name="safety.manage").delete()
    response = as_user(api_client, world.om_tokyo).get(ALERTS)
    assert all(item["available_actions"] == [] for item in response.data["results"])


# --- Alert filters, ordering, pagination ------------------------------------------


def test_alert_filters(api_client, world):
    client = as_user(api_client, world.admin)
    assert ids(client.get(ALERTS, {"severity": "critical"})) == {str(world.alert_tokyo_quake.pk), str(world.alert_tokyo_flood.pk)}
    assert client.get(ALERTS, {"severity": "high"}).data["count"] == 2
    assert client.get(ALERTS, {"status": "new"}).data["count"] == 4
    assert ids(client.get(ALERTS, {"hazard_type": "flood"})) == {str(world.alert_tokyo_flood.pk)}
    assert ids(client.get(ALERTS, {"provider": "gdacs"})) == {str(world.alert_tokyo_flood.pk)}
    assert client.get(ALERTS, {"hazard_withdrawn": "true"}).data["count"] == 0
    assert client.get(ALERTS, {"hazard_withdrawn": "false"}).data["count"] == 4
    assert client.get(ALERTS, {"created_after": "2000-01-01T00:00:00Z", "created_before": "2999-01-01T00:00:00Z"}).data["count"] == 4
    assert client.get(ALERTS, {"created_after": "2999-01-01T00:00:00Z"}).data["count"] == 0


@pytest.mark.parametrize(
    "params",
    [
        {"status": "open"},
        {"severity": "extreme"},
        {"provider": "twitter"},
        {"project": "not-a-uuid"},
        {"created_after": "yesterday"},
        {"created_after": "2026-09-16T00:00:00Z", "created_before": "2026-09-15T00:00:00Z"},
    ],
)
def test_invalid_alert_filters_return_validation_errors(api_client, world, params):
    response = as_user(api_client, world.admin).get(ALERTS, params)
    assert response.status_code == 400
    assert response.data["success"] is False


def test_alert_ordering_and_unknown_ordering_fields(api_client, world):
    client = as_user(api_client, world.admin)
    distances = [float(item["distance_km"]) for item in client.get(ALERTS, {"ordering": "distance_km"}).data["results"]]
    assert distances == sorted(distances)
    assert client.get(ALERTS, {"ordering": "project__facility__name"}).status_code == 200


def test_alert_pagination_uses_standard_envelope_and_bounds(api_client, world):
    client = as_user(api_client, world.admin)
    page = client.get(ALERTS, {"page_size": 1})
    assert set(page.data) == {"count", "total_pages", "current_page", "page_size", "next", "previous", "results"}
    assert (page.data["count"], page.data["total_pages"], len(page.data["results"])) == (4, 4, 1)
    assert client.get(ALERTS, {"page_size": 100000}).data["page_size"] == 100


# --- Hazard events ------------------------------------------------------------------


def test_hazard_events_are_scoped_through_alerts(api_client, world):
    expected = {
        world.cm_cairo: {world.event_cairo.pk},
        world.om_cairo: {world.event_cairo.pk},
        world.om_tokyo: {world.event_tokyo.pk, world.event_flood.pk},
        world.admin: {world.event_cairo.pk, world.event_tokyo.pk, world.event_flood.pk},
    }
    for user, event_ids in expected.items():
        assert ids(as_user(api_client, user).get(EVENTS)) == {str(pk) for pk in event_ids}
    assert as_user(api_client, world.cm_cairo).get(f"{EVENTS}{world.event_tokyo.pk}/").status_code == 404
    assert as_user(api_client, world.om_tokyo).get(f"{EVENTS}{world.event_flood.pk}/").status_code == 200
    assert as_user(api_client, world.admin).get(f"{EVENTS}{uuid.uuid4()}/").status_code == 404


def test_hazard_event_detail_contract_excludes_payload(api_client, world):
    response = as_user(api_client, world.admin).get(f"{EVENTS}{world.event_flood.pk}/")
    assert response.status_code == 200
    assert "payload" not in response.data and "last_seen_at" not in response.data
    assert response.data["provider_event_id"] == "FL:1000999"
    assert response.data["source_url"].startswith("https://www.gdacs.org/")
    assert PAYLOAD_MARKER not in response.content.decode()


def test_hazard_event_filters_and_pagination(api_client, world):
    client = as_user(api_client, world.admin)
    assert ids(client.get(EVENTS, {"provider": "gdacs"})) == {str(world.event_flood.pk)}
    assert client.get(EVENTS, {"hazard_type": "earthquake"}).data["count"] == 2
    assert ids(client.get(EVENTS, {"alert_level": "red"})) == {str(world.event_flood.pk)}
    assert client.get(EVENTS, {"provider_status": "active"}).data["count"] == 3
    assert ids(client.get(EVENTS, {"project": str(world.operational_tokyo.pk)})) == {str(world.event_tokyo.pk), str(world.event_flood.pk)}
    assert client.get(EVENTS, {"occurred_after": "2999-01-01T00:00:00Z"}).data["count"] == 0
    assert client.get(EVENTS, {"occurred_after": "2026-09-16T00:00:00Z", "occurred_before": "2026-09-15T00:00:00Z"}).status_code == 400
    assert client.get(EVENTS, {"alert_level": "purple"}).status_code == 400
    page = client.get(EVENTS, {"page_size": 2})
    assert (page.data["count"], len(page.data["results"])) == (3, 2)


# --- Coverage and method restrictions --------------------------------------------------


def test_monitoring_coverage_is_scoped_and_reports_kill_switch(api_client, world, settings):
    assert as_user(api_client, world.admin).get(COVERAGE).data == {
        "monitored_projects": 4,
        "projects_with_coordinates": 3,
        "projects_missing_coordinates": 1,
        "alert_creation_enabled": True,
    }
    assert as_user(api_client, world.cm_cairo).get(COVERAGE).data["monitored_projects"] == 1
    assert as_user(api_client, world.om_tokyo).get(COVERAGE).data["monitored_projects"] == 1
    settings.SAFETY_ALERTS_ENABLED = False
    set_setting("safety.externalAlerts", False)
    assert as_user(api_client, world.admin).get(COVERAGE).data["alert_creation_enabled"] is False


def test_read_endpoints_reject_writes_and_no_ingestion_route_exists(api_client, world):
    client = as_user(api_client, world.admin)
    detail = f"{ALERTS}{world.alert_construction.pk}/"
    assert client.post(ALERTS, {}, format="json").status_code == 405
    assert client.put(detail, {"severity": "low"}, format="json").status_code == 405
    assert client.patch(detail, {"status": "closed"}, format="json").status_code == 405
    assert client.delete(detail).status_code == 405
    assert client.post(EVENTS, {"provider": "usgs"}, format="json").status_code == 405
    assert client.patch(f"{EVENTS}{world.event_cairo.pk}/", {"provider": "gdacs"}, format="json").status_code == 405
    assert client.post(COVERAGE, {}, format="json").status_code == 405
    assert client.post("/api/v1/safety/ingest/", {}, format="json").status_code == 404
    world.alert_construction.refresh_from_db()
    assert world.alert_construction.status == "new"


def test_other_role_without_assignments_sees_nothing(api_client, world):
    unassigned_om = make_user(Role.OPERATIONS_MANAGER, "om-unassigned")
    client = as_user(api_client, unassigned_om)
    assert client.get(ALERTS).data["count"] == 0
    assert client.get(EVENTS).data["count"] == 0
    assert client.get(COVERAGE).data["monitored_projects"] == 0
