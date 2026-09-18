"""The human decision workflow: propose, then a General Manager rules.

An external hazard is information. These tests pin the rule that it never
becomes an instruction on its own, that the two protective workflows stay in
separate hands, and that only an approved worker-protection proposal can reach
a person over Telegram.
"""

import uuid
from datetime import date
from unittest.mock import patch

import pytest

from api.v1.safety.tests.world import build_world
from apps.assets.models import Asset
from apps.audit.models import AuditLog
from apps.safety.models import (
    ProjectSafetyAlert,
    ProjectTelegramDestination,
    SafetyActionProposal,
    SafetyTelegramDelivery,
)
from apps.safety.proposals import REJECTION_TITLE_AR
from apps.safety.tests.helpers import make_user
from apps.projects.models import ProjectAssignment
from apps.users.models import Role


pytestmark = pytest.mark.django_db

ALERTS = "/api/v1/safety/alerts/"
PROPOSALS = "/api/v1/safety/action-proposals/"

WORKER = SafetyActionProposal.DecisionType.WORKER_PROTECTION
ASSET = SafetyActionProposal.DecisionType.ASSET_PROTECTION


@pytest.fixture
def world(settings, super_admin_user):
    return build_world(settings, super_admin_user)


@pytest.fixture
def telegram_on(settings):
    settings.SAFETY_TELEGRAM_ENABLED = True
    return settings


def propose(api_client, user, alert, decision_type, **overrides):
    payload = {
        "decision_type": decision_type,
        "proposed_action": "suspend_outdoor_work",
        "notes": "Protect the crew while the hazard is overhead.",
        **overrides,
    }
    api_client.force_authenticate(user)
    return api_client.post(f"{ALERTS}{alert.pk}/proposals/", payload, format="json")


def rule(api_client, user, proposal_id, verdict, data=None):
    api_client.force_authenticate(user)
    return api_client.post(f"{PROPOSALS}{proposal_id}/{verdict}/", data or {}, format="json")


def rule_committed(api_client, user, proposal_id, verdict, capture, data=None):
    """Rule on a proposal and run its post-commit hooks.

    Dispatch is deliberately scheduled with ``transaction.on_commit`` so no
    Telegram outcome can roll a ruling back; in a test the surrounding
    transaction never commits, so the hooks have to be run explicitly.
    """

    with capture(execute=True):
        response = rule(api_client, user, proposal_id, verdict, data)
    return response


def audit_actions(entity_id, prefix):
    return list(
        AuditLog.objects.filter(entity_id=str(entity_id), action__startswith=prefix)
        .order_by("created_at", "id")
        .values_list("action", flat=True)
    )


def make_asset(facility, admin, name):
    """A minimal valid Asset inside one facility."""

    suffix = uuid.uuid4().hex[:8]
    return Asset.objects.create(
        facility=facility,
        name=name,
        asset_type="hvac",
        category="mechanical",
        serial_number=f"SN-{suffix}",
        manufacturer="ACME",
        model="X1",
        location_inside_facility="Roof",
        installation_date=date(2024, 1, 1),
        created_by=admin,
    )


def add_destination(project, admin, *, chat_id="700100200", name="crew channel", enabled=True):
    """The Telegram channel an approved worker instruction is addressed to."""

    return ProjectTelegramDestination.objects.create(
        project=project,
        chat_id=chat_id,
        display_name=name,
        is_enabled=enabled,
        created_by=admin,
    )


# ---------------------------------------------------------------------------
# Visibility (1, 2)
# ---------------------------------------------------------------------------


def test_managers_see_hazards_for_their_own_scope_only(api_client, world):
    api_client.force_authenticate(world.om_cairo)
    body = api_client.get(ALERTS).json()
    projects = {row["project"]["id"] for row in body["results"]}

    assert str(world.operational_cairo.pk) in projects
    # Tokyo is another Operations Manager's facility.
    assert str(world.operational_tokyo.pk) not in projects


def test_out_of_scope_alert_is_not_found_for_a_manager(api_client, world):
    api_client.force_authenticate(world.om_cairo)
    assert api_client.get(f"{ALERTS}{world.alert_tokyo_quake.pk}/").status_code == 404


# ---------------------------------------------------------------------------
# Proposing: the two workflows are separate responsibilities (3, 4)
# ---------------------------------------------------------------------------


def test_construction_manager_proposes_worker_protection(api_client, world):
    response = propose(api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER)

    assert response.status_code == 201
    body = response.json()
    assert body["decision_type"] == WORKER
    assert body["status"] == "pending_manager_review"
    # The proposer may not rule on it.
    assert body["can_review"] is False
    assert audit_actions(body["id"], "safety_proposal.") == [
        "safety_proposal.worker_protection.proposed"
    ]


def test_operations_manager_proposes_asset_protection_with_facility_assets(
    api_client, world
):
    asset = make_asset(world.facility_cairo, world.admin, "Chiller A")
    response = propose(
        api_client,
        world.om_cairo,
        world.alert_operational_cairo,
        ASSET,
        proposed_action="increase_precautions",
        notes="Reduce non-essential equipment load during the heat window.",
        asset_ids=[str(asset.pk)],
    )

    assert response.status_code == 201
    body = response.json()
    assert body["decision_type"] == ASSET
    assert [a["id"] for a in body["affected_assets"]] == [str(asset.pk)]


def test_neither_manager_can_propose_in_the_others_name(api_client, world):
    # Construction Manager speaks for people, not for facility equipment.
    assert propose(api_client, world.cm_tokyo, world.alert_tokyo_quake, ASSET).status_code == 403
    # Operations Manager speaks for equipment, not for the site's workers.
    assert propose(
        api_client, world.om_cairo, world.alert_operational_cairo, WORKER
    ).status_code == 403


def test_asset_ids_are_confined_to_the_projects_own_facility(api_client, world):
    other_facility_asset = make_asset(
        world.alert_tokyo_quake.project.facility, world.admin, "Foreign pump"
    )
    response = propose(
        api_client,
        world.om_cairo,
        world.alert_operational_cairo,
        ASSET,
        asset_ids=[str(other_facility_asset.pk)],
    )

    assert response.status_code == 409
    assert SafetyActionProposal.objects.count() == 0


# ---------------------------------------------------------------------------
# Separation of duties (5)
# ---------------------------------------------------------------------------


def test_a_manager_cannot_approve_or_reject_their_own_proposal(api_client, world):
    proposal_id = propose(
        api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER
    ).json()["id"]

    assert rule(api_client, world.cm_tokyo, proposal_id, "approve").status_code == 403
    assert rule(
        api_client, world.cm_tokyo, proposal_id, "reject", {"reason": "no"}
    ).status_code == 403
    assert SafetyActionProposal.objects.get(pk=proposal_id).status == "pending_manager_review"


def test_a_peer_manager_cannot_rule_on_someone_elses_proposal(api_client, world):
    proposal_id = propose(
        api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER
    ).json()["id"]

    # In scope to see it, but without approval authority.
    assert rule(api_client, world.om_tokyo, proposal_id, "approve").status_code == 403
    assert SafetyActionProposal.objects.get(pk=proposal_id).status == "pending_manager_review"


def test_the_direct_decide_shortcut_is_closed_to_managers(api_client, world):
    """A manager cannot reach `actioned` -- and Telegram -- on their own."""

    api_client.force_authenticate(world.cm_tokyo)
    api_client.post(f"{ALERTS}{world.alert_tokyo_quake.pk}/acknowledge/", {}, format="json")
    response = api_client.post(
        f"{ALERTS}{world.alert_tokyo_quake.pk}/decide/",
        {"decision": "monitor"},
        format="json",
    )

    assert response.status_code == 403
    assert ProjectSafetyAlert.objects.get(pk=world.alert_tokyo_quake.pk).status == "acknowledged"


# ---------------------------------------------------------------------------
# The General Manager's review queue (6)
# ---------------------------------------------------------------------------


def test_general_manager_sees_pending_proposals_across_projects(api_client, world):
    worker_id = propose(
        api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER
    ).json()["id"]
    asset_id = propose(
        api_client, world.om_cairo, world.alert_operational_cairo, ASSET
    ).json()["id"]

    api_client.force_authenticate(world.admin)
    body = api_client.get(f"{PROPOSALS}?status=pending_manager_review").json()
    rows = {row["id"]: row for row in body["results"]}

    assert {worker_id, asset_id} <= set(rows)
    assert rows[worker_id]["can_review"] is True
    assert rows[asset_id]["can_review"] is True


def test_a_manager_only_sees_proposals_on_their_own_projects(api_client, world):
    tokyo_id = propose(
        api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER
    ).json()["id"]

    api_client.force_authenticate(world.om_cairo)
    listed = {row["id"] for row in api_client.get(PROPOSALS).json()["results"]}
    assert tokyo_id not in listed
    assert api_client.get(f"{PROPOSALS}{tokyo_id}/").status_code == 404


# ---------------------------------------------------------------------------
# Worker protection: approval dispatches, rejection does not (7, 8, 9, 10, 13)
# ---------------------------------------------------------------------------


def test_approved_worker_protection_actions_the_alert_and_queues_the_instruction(
    api_client, world, telegram_on, django_capture_on_commit_callbacks
):
    add_destination(world.operational_tokyo, world.admin)
    proposal_id = propose(
        api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER
    ).json()["id"]

    with patch("apps.safety.telegram.is_configured", return_value=True), patch(
        "apps.safety.telegram_tasks.deliver_safety_telegram_message.delay"
    ) as delay:
        response = rule_committed(
            api_client, world.admin, proposal_id, "approve",
            django_capture_on_commit_callbacks,
        )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    alert = ProjectSafetyAlert.objects.get(pk=world.alert_tokyo_quake.pk)
    assert (alert.status, alert.decision, alert.decided_by_id) == (
        "actioned",
        "suspend_outdoor_work",
        world.admin.pk,
    )
    assert delay.call_count == 1
    delivery = SafetyTelegramDelivery.all_objects.get()
    assert delivery.proposal_id is not None
    assert delivery.project_destination.project_id == world.operational_tokyo.pk
    assert delivery.recipient_id is None
    assert delivery.event_key.startswith("worker_protection_approved:")


def test_rejected_worker_protection_dispatches_nothing_and_leaves_the_alert_alone(
    api_client, world, telegram_on, django_capture_on_commit_callbacks
):
    add_destination(world.operational_tokyo, world.admin)
    proposal_id = propose(
        api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER
    ).json()["id"]

    with patch("apps.safety.telegram.is_configured", return_value=True), patch(
        "apps.safety.telegram_tasks.deliver_safety_telegram_message.delay"
    ) as delay:
        response = rule_committed(
            api_client, world.admin, proposal_id, "reject",
            django_capture_on_commit_callbacks,
            {"reason": "The crew is already off site for the day."},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert delay.call_count == 0
    assert SafetyTelegramDelivery.all_objects.count() == 0
    assert ProjectSafetyAlert.objects.get(pk=world.alert_tokyo_quake.pk).status != "actioned"


def test_rejection_requires_a_reason(api_client, world):
    proposal_id = propose(
        api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER
    ).json()["id"]

    assert rule(api_client, world.admin, proposal_id, "reject", {"reason": "  "}).status_code == 400
    assert SafetyActionProposal.objects.get(pk=proposal_id).status == "pending_manager_review"


def test_the_instruction_carries_the_approved_action_not_an_unapproved_ask(
    api_client, world, telegram_on, django_capture_on_commit_callbacks
):
    from apps.safety.telegram_delivery import build_worker_instruction_message

    add_destination(world.operational_tokyo, world.admin)
    proposal_id = propose(
        api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER
    ).json()["id"]
    with patch("apps.safety.telegram.is_configured", return_value=True), patch(
        "apps.safety.telegram_tasks.deliver_safety_telegram_message.delay"
    ):
        rule_committed(
            api_client, world.admin, proposal_id, "approve",
            django_capture_on_commit_callbacks,
        )

    message = build_worker_instruction_message(
        SafetyActionProposal.objects.select_related(
            "alert__project", "reviewed_by"
        ).get(pk=proposal_id)
    )
    assert "قرار سلامة معتمد" in message
    assert world.alert_tokyo_quake.project.name in message
    assert "إيقاف الأعمال الخارجية مؤقتاً" in message
    assert "نظام SFLMS" in message
    # No provider payload, no identifiers, no links, no secrets.
    assert "http" not in message
    assert str(world.alert_tokyo_quake.pk) not in message


# ---------------------------------------------------------------------------
# Asset protection is audited, never dispatched (11, 12)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "verdict,data,expected",
    [
        ("approve", {}, "approved"),
        ("reject", {"reason": "Maintenance window cannot move."}, "rejected"),
    ],
)
def test_asset_protection_rulings_are_recorded_without_any_message(
    api_client, world, telegram_on, django_capture_on_commit_callbacks,
    verdict, data, expected,
):
    add_destination(world.operational_cairo, world.admin)
    proposal_id = propose(
        api_client, world.om_cairo, world.alert_operational_cairo, ASSET
    ).json()["id"]

    with patch("apps.safety.telegram.is_configured", return_value=True), patch(
        "apps.safety.telegram_tasks.deliver_safety_telegram_message.delay"
    ) as delay:
        response = rule_committed(
            api_client, world.admin, proposal_id, verdict,
            django_capture_on_commit_callbacks, data,
        )

    assert response.status_code == 200
    assert response.json()["status"] == expected
    # Approving asset protection never reaches a person, and never silently
    # shuts anything down.
    assert delay.call_count == 0
    assert SafetyTelegramDelivery.all_objects.count() == 0
    assert ProjectSafetyAlert.objects.get(
        pk=world.alert_operational_cairo.pk
    ).status != "actioned"
    assert audit_actions(proposal_id, "safety_proposal.") == [
        "safety_proposal.asset_protection.proposed",
        f"safety_proposal.asset_protection.{expected}",
    ]


# ---------------------------------------------------------------------------
# Idempotency (14)
# ---------------------------------------------------------------------------


def test_approving_twice_does_not_produce_a_second_instruction(
    api_client, world, telegram_on, django_capture_on_commit_callbacks
):
    add_destination(world.operational_tokyo, world.admin)
    proposal_id = propose(
        api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER
    ).json()["id"]

    with patch("apps.safety.telegram.is_configured", return_value=True), patch(
        "apps.safety.telegram_tasks.deliver_safety_telegram_message.delay"
    ) as delay:
        first = rule_committed(
            api_client, world.admin, proposal_id, "approve",
            django_capture_on_commit_callbacks,
        )
        second = rule_committed(
            api_client, world.admin, proposal_id, "approve",
            django_capture_on_commit_callbacks,
        )

    assert first.status_code == 200
    assert second.status_code == 409
    assert delay.call_count == 1
    assert SafetyTelegramDelivery.all_objects.count() == 1


def test_a_rejected_proposal_cannot_later_be_approved(api_client, world):
    proposal_id = propose(
        api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER
    ).json()["id"]
    rule(api_client, world.admin, proposal_id, "reject", {"reason": "Not warranted."})

    assert rule(api_client, world.admin, proposal_id, "approve").status_code == 409
    assert SafetyActionProposal.objects.get(pk=proposal_id).status == "rejected"


def test_only_one_open_proposal_of_a_kind_per_alert(api_client, world):
    assert propose(api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER).status_code == 201
    assert propose(api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER).status_code == 409

    # Once ruled on, the alert can receive a fresh proposal.
    proposal = SafetyActionProposal.objects.get()
    rule(api_client, world.admin, proposal.pk, "reject", {"reason": "Superseded."})
    assert propose(api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER).status_code == 201


# ---------------------------------------------------------------------------
# Unauthorized access (15)
# ---------------------------------------------------------------------------


def test_security_officer_and_anonymous_users_are_refused(api_client, world):
    assert propose(api_client, world.officer, world.alert_operational_cairo, WORKER).status_code == 403

    api_client.force_authenticate(None)
    assert api_client.get(PROPOSALS).status_code == 401
    assert api_client.post(
        f"{ALERTS}{world.alert_tokyo_quake.pk}/proposals/", {}, format="json"
    ).status_code == 401
    assert SafetyActionProposal.objects.count() == 0


def test_a_manager_cannot_propose_on_a_project_outside_their_assignments(api_client, world):
    assert propose(api_client, world.cm_cairo, world.alert_tokyo_quake, WORKER).status_code == 404
    assert SafetyActionProposal.objects.count() == 0


# ---------------------------------------------------------------------------
# Hazard detection alone is inert (17, 18, 19)
# ---------------------------------------------------------------------------


def test_detecting_a_hazard_creates_alerts_but_never_a_proposal_or_a_message(
    api_client, world, telegram_on
):
    """The world fixture has already ingested live-shaped provider events."""

    add_destination(world.operational_tokyo, world.admin)


    assert ProjectSafetyAlert.objects.exists()
    # Ingestion produced information only.
    assert SafetyActionProposal.objects.count() == 0
    assert SafetyTelegramDelivery.all_objects.count() == 0
    assert not ProjectSafetyAlert.objects.filter(status="actioned").exists()


def test_the_existing_alert_lifecycle_still_works_for_the_general_manager(
    api_client, world
):
    """acknowledge -> decide -> close is unchanged for the approving role."""

    alert = world.alert_tokyo_flood
    api_client.force_authenticate(world.admin)
    base = f"{ALERTS}{alert.pk}/"

    assert api_client.post(f"{base}acknowledge/", {}, format="json").status_code == 200
    assert api_client.post(
        f"{base}decide/", {"decision": "monitor"}, format="json"
    ).status_code == 200
    assert api_client.post(f"{base}close/", {}, format="json").status_code == 200
    assert ProjectSafetyAlert.objects.get(pk=alert.pk).status == "closed"


def test_unrelated_project_channels_are_never_messaged(
    api_client, world, telegram_on, django_capture_on_commit_callbacks
):
    """Project A's decision reaches Project A's channel and nothing else."""

    add_destination(world.operational_tokyo, world.admin, chat_id="700100201")
    unrelated = add_destination(world.operational_cairo, world.admin, chat_id="700100202")
    proposal_id = propose(
        api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER
    ).json()["id"]

    with patch("apps.safety.telegram.is_configured", return_value=True), patch(
        "apps.safety.telegram_tasks.deliver_safety_telegram_message.delay"
    ):
        rule_committed(
            api_client, world.admin, proposal_id, "approve",
            django_capture_on_commit_callbacks,
        )

    addressed = set(
        SafetyTelegramDelivery.all_objects.values_list("project_destination_id", flat=True)
    )
    # Tokyo's channel only. Cairo is a different project.
    assert unrelated.pk not in addressed
    assert len(addressed) == 1


def test_a_disabled_project_channel_is_not_used(
    api_client, world, telegram_on, django_capture_on_commit_callbacks
):
    add_destination(world.operational_tokyo, world.admin, enabled=False)
    proposal_id = propose(
        api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER
    ).json()["id"]

    with patch("apps.safety.telegram.is_configured", return_value=True), patch(
        "apps.safety.telegram_tasks.deliver_safety_telegram_message.delay"
    ) as delay:
        rule_committed(
            api_client, world.admin, proposal_id, "approve",
            django_capture_on_commit_callbacks,
        )

    assert delay.call_count == 0
    assert SafetyTelegramDelivery.all_objects.count() == 0


# ---------------------------------------------------------------------------
# Audit (16)
# ---------------------------------------------------------------------------


def test_every_human_decision_is_audited_with_actor_and_outcome(api_client, world):
    proposal_id = propose(
        api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER
    ).json()["id"]
    rule(api_client, world.admin, proposal_id, "reject", {"reason": "Crew already clear."})

    rows = list(
        AuditLog.objects.filter(entity_id=str(proposal_id))
        .order_by("created_at", "id")
        .values("action", "actor_id", "after")
    )
    assert [row["action"] for row in rows] == [
        "safety_proposal.worker_protection.proposed",
        "safety_proposal.worker_protection.rejected",
    ]
    assert rows[0]["actor_id"] == world.cm_tokyo.pk
    assert rows[1]["actor_id"] == world.admin.pk
    assert rows[1]["after"]["status"] == "rejected"
    assert rows[1]["after"]["decision_type"] == "worker_protection"


# ---------------------------------------------------------------------------
# The General Manager approves; they never propose
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("decision_type", [WORKER, ASSET])
def test_the_general_manager_cannot_create_either_kind_of_proposal(
    api_client, world, decision_type
):
    """Separation of duties made structural rather than procedural.

    The approver has nothing to raise, so there is no proposal they could be
    asked to rule on their own. `user_has_permission` short-circuits to True
    for Super Admin, so this has to be refused explicitly rather than relying
    on which permissions were granted.
    """

    response = propose(api_client, world.admin, world.alert_tokyo_quake, decision_type)

    assert response.status_code == 403
    assert SafetyActionProposal.objects.count() == 0


def test_the_general_manager_is_offered_no_proposal_controls(api_client, world):
    api_client.force_authenticate(world.admin)
    body = api_client.get(f"{ALERTS}{world.alert_tokyo_quake.pk}/").json()

    assert body["available_proposal_types"] == []


def test_each_manager_is_offered_only_their_own_kind(api_client, world):
    api_client.force_authenticate(world.cm_tokyo)
    cm_body = api_client.get(f"{ALERTS}{world.alert_tokyo_quake.pk}/").json()
    assert cm_body["available_proposal_types"] == ["worker_protection"]

    api_client.force_authenticate(world.om_tokyo)
    om_body = api_client.get(f"{ALERTS}{world.alert_tokyo_quake.pk}/").json()
    assert om_body["available_proposal_types"] == ["asset_protection"]


# ---------------------------------------------------------------------------
# Detail the approver needs in order to rule
# ---------------------------------------------------------------------------


def test_a_proposal_carries_its_window_and_worker_scope(api_client, world):
    response = propose(
        api_client,
        world.cm_tokyo,
        world.alert_tokyo_quake,
        WORKER,
        effective_from="2026-09-20T09:00:00Z",
        effective_until="2026-09-20T13:00:00Z",
        worker_scope="Outdoor crews",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["effective_from"].startswith("2026-09-20T09:00")
    assert body["effective_until"].startswith("2026-09-20T13:00")
    assert body["worker_scope"] == "Outdoor crews"


def test_a_window_that_ends_before_it_starts_is_refused(api_client, world):
    response = propose(
        api_client,
        world.cm_tokyo,
        world.alert_tokyo_quake,
        WORKER,
        effective_from="2026-09-20T13:00:00Z",
        effective_until="2026-09-20T09:00:00Z",
    )

    assert response.status_code == 400
    assert SafetyActionProposal.objects.count() == 0


# ---------------------------------------------------------------------------
# A rejection reaches the manager who asked
# ---------------------------------------------------------------------------


def test_rejection_notifies_the_proposing_manager_with_the_reason(
    api_client, world, django_capture_on_commit_callbacks
):
    from apps.notifications.models import Notification

    proposal_id = propose(
        api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER
    ).json()["id"]
    reason = "Conditions do not currently warrant suspending work."

    rule_committed(
        api_client, world.admin, proposal_id, "reject",
        django_capture_on_commit_callbacks,
        {"reason": reason},
    )

    notification = Notification.objects.get(recipient=world.cm_tokyo, category="safety")
    assert notification.title == REJECTION_TITLE_AR["worker_protection"]
    assert reason in notification.body
    # The approver is not notified of their own ruling.
    assert not Notification.objects.filter(recipient=world.admin, category="safety").exists()


def test_an_asset_rejection_names_the_asset_workflow(
    api_client, world, django_capture_on_commit_callbacks
):
    from apps.notifications.models import Notification

    proposal_id = propose(
        api_client, world.om_cairo, world.alert_operational_cairo, ASSET
    ).json()["id"]
    rule_committed(
        api_client, world.admin, proposal_id, "reject",
        django_capture_on_commit_callbacks,
        {"reason": "Maintenance window cannot be moved."},
    )

    notification = Notification.objects.get(recipient=world.om_cairo, category="safety")
    assert notification.title == REJECTION_TITLE_AR["asset_protection"]


# ---------------------------------------------------------------------------
# Delivery state is honest about what actually happened
# ---------------------------------------------------------------------------


def test_a_project_without_a_channel_records_no_delivery_and_keeps_the_approval(
    api_client, world, telegram_on, django_capture_on_commit_callbacks
):
    """Unreachable is not delivered, and must never look like it."""

    proposal_id = propose(
        api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER
    ).json()["id"]

    with patch("apps.safety.telegram.is_configured", return_value=True), patch(
        "apps.safety.telegram_tasks.deliver_safety_telegram_message.delay"
    ) as delay:
        response = rule_committed(
            api_client, world.admin, proposal_id, "approve",
            django_capture_on_commit_callbacks,
        )

    assert response.json()["status"] == "approved"
    assert delay.call_count == 0
    assert SafetyTelegramDelivery.all_objects.count() == 0
    # The decision itself still stands.
    assert ProjectSafetyAlert.objects.get(pk=world.alert_tokyo_quake.pk).status == "actioned"


def test_telegram_switched_off_never_records_a_send(
    api_client, world, settings, django_capture_on_commit_callbacks
):
    settings.SAFETY_TELEGRAM_ENABLED = False
    add_destination(world.operational_tokyo, world.admin)
    proposal_id = propose(
        api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER
    ).json()["id"]

    rule_committed(
        api_client, world.admin, proposal_id, "approve",
        django_capture_on_commit_callbacks,
    )

    assert not SafetyTelegramDelivery.all_objects.filter(status="sent").exists()
    assert SafetyActionProposal.objects.get(pk=proposal_id).status == "approved"


def test_a_telegram_api_failure_is_recorded_as_failed_not_sent(
    api_client, world, telegram_on, django_capture_on_commit_callbacks
):
    from apps.safety import telegram as telegram_module
    from apps.safety.telegram_tasks import deliver_safety_telegram_message

    add_destination(world.operational_tokyo, world.admin)
    proposal_id = propose(
        api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER
    ).json()["id"]
    with patch("apps.safety.telegram.is_configured", return_value=True), patch(
        "apps.safety.telegram_tasks.deliver_safety_telegram_message.delay"
    ):
        rule_committed(
            api_client, world.admin, proposal_id, "approve",
            django_capture_on_commit_callbacks,
        )

    delivery = SafetyTelegramDelivery.all_objects.get()
    failure = telegram_module.TelegramError("telegram_invalid_chat", retryable=False)
    with patch("apps.safety.telegram.is_configured", return_value=True), patch(
        "apps.safety.telegram.send_message", side_effect=failure
    ):
        result = deliver_safety_telegram_message(str(delivery.pk))

    assert result == "failed"
    delivery.refresh_from_db()
    assert (delivery.status, delivery.sent_at) == ("failed", None)
    assert delivery.failure_code == "telegram_invalid_chat"


def test_a_successful_send_is_recorded_as_sent_and_never_repeated(
    api_client, world, telegram_on, django_capture_on_commit_callbacks
):
    from apps.safety.telegram_tasks import deliver_safety_telegram_message

    add_destination(world.operational_tokyo, world.admin)
    proposal_id = propose(
        api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER
    ).json()["id"]
    with patch("apps.safety.telegram.is_configured", return_value=True), patch(
        "apps.safety.telegram_tasks.deliver_safety_telegram_message.delay"
    ):
        rule_committed(
            api_client, world.admin, proposal_id, "approve",
            django_capture_on_commit_callbacks,
        )

    delivery = SafetyTelegramDelivery.all_objects.get()
    sends = []
    with patch("apps.safety.telegram.is_configured", return_value=True), patch(
        "apps.safety.telegram.send_message",
        side_effect=lambda **kwargs: sends.append(kwargs["chat_id"]) or "42",
    ):
        assert deliver_safety_telegram_message(str(delivery.pk)) == "sent"
        # A replayed task must not produce a second message.
        deliver_safety_telegram_message(str(delivery.pk))

    delivery.refresh_from_db()
    assert delivery.status == "sent"
    assert delivery.sent_at is not None
    assert delivery.provider_message_id == "42"
    assert len(sends) == 1
    assert sends == ["700100200"]


def test_no_bot_token_appears_in_any_stored_or_returned_value(
    api_client, world, settings, django_capture_on_commit_callbacks
):
    """The token belongs in settings and in the outbound URL, nowhere else."""

    from apps.audit.models import AuditLog

    token = "999999:SECRET-BOT-TOKEN-DO-NOT-LEAK"
    settings.SAFETY_TELEGRAM_ENABLED = True
    settings.SAFETY_TELEGRAM_BOT_TOKEN = token
    add_destination(world.operational_tokyo, world.admin)
    created = propose(api_client, world.cm_tokyo, world.alert_tokyo_quake, WORKER)
    proposal_id = created.json()["id"]

    with patch("apps.safety.telegram.send_message", return_value="42"):
        approved = rule_committed(
            api_client, world.admin, proposal_id, "approve",
            django_capture_on_commit_callbacks,
        )

    assert token not in created.content.decode()
    assert token not in approved.content.decode()
    for delivery in SafetyTelegramDelivery.all_objects.all():
        blob = f"{delivery.event_key}{delivery.failure_code}{delivery.provider_message_id}"
        assert token not in blob
    for row in AuditLog.objects.all():
        assert token not in f"{row.before}{row.after}"
