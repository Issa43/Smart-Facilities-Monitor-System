import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from apps.audit.models import AuditLog
from apps.facilities.models import Facility, FacilityAssignment
from apps.notifications.models import Notification
from apps.security.camera_events import CameraEventConflict, create_camera_event, update_camera_event
from apps.security.machine_credentials import create_ai_ingestion_credential
from apps.security.models import Camera, CameraEvent, SecurityAlert
from apps.security.realtime import (
    broadcast_camera_event_created,
    camera_event_created_contract,
    schedule_camera_event_created_broadcast,
    security_alert_updated_contract,
    security_user_group,
)
from apps.security.services import (
    convert_alert_to_incident,
    dismiss_security_alert,
    review_security_alert,
)
from apps.users.models import User
from config.asgi import application


pytestmark = pytest.mark.django_db(transaction=True)
ORIGIN_HEADERS = [(b"origin", b"http://localhost")]


def make_user(role, suffix):
    return User.objects.create_user(
        email=f"live-{suffix}@sflms.test",
        username=f"live-{suffix}",
        full_name=f"Live {suffix}",
        password="StrongPass123!",
        role=role,
    )


def make_camera(actor, suffix):
    facility = Facility.objects.create(
        name=f"Live Facility {suffix}",
        type=Facility.Type.INDUSTRIAL,
        location="Riyadh",
        created_by=actor,
    )
    camera = Camera.objects.create(
        facility=facility,
        code=f"LIVE-{suffix}",
        name=f"Live Camera {suffix}",
        zone="Gate",
        status=Camera.Status.ONLINE,
        created_by=actor,
    )
    return facility, camera


def make_machine(actor, camera):
    return create_ai_ingestion_credential(
        name="Live event producer",
        actor=actor,
        cameras=[camera],
        expires_at=timezone.now() + timedelta(days=30),
    )[0]


def access_token(user):
    return str(AccessToken.for_user(user))


def make_event(actor, camera, *, event_type="fire_alert", authorized=None):
    credential = make_machine(actor, camera)
    alert = None
    if authorized is not True:
        alert_type = {
            "fire_alert": SecurityAlert.AlertType.FIRE,
            "smoke_alert": SecurityAlert.AlertType.SMOKE,
            "intrusion_alert": SecurityAlert.AlertType.INTRUSION,
            "vehicle_entry": SecurityAlert.AlertType.VEHICLE,
            "vehicle_exit": SecurityAlert.AlertType.VEHICLE,
            "tamper_alert": SecurityAlert.AlertType.TAMPER,
        }[event_type]
        alert = SecurityAlert.objects.create(
            facility=camera.facility,
            alert_type=alert_type,
            location=camera.zone,
            severity_level=(
                SecurityAlert.Severity.HIGH
                if event_type in {"vehicle_entry", "vehicle_exit", "intrusion_alert"}
                else SecurityAlert.Severity.CRITICAL
            ),
            source=SecurityAlert.Source.AI_DETECTION,
        )
    return CameraEvent.objects.create(
        event_type=event_type,
        camera=camera,
        ingestion_credential=credential,
        source_event_id=uuid.uuid4(),
        detected_at=timezone.now(),
        direction=("entry" if event_type == "vehicle_entry" else None),
        plate_number=("ABC-123" if event_type == "vehicle_entry" else None),
        authorized=authorized,
        security_alert=alert,
        created_by=credential.principal,
    )


def communicator(token=None, *, path="/ws/security/events/"):
    subprotocols = ["sflms.jwt", token] if token else []
    return WebsocketCommunicator(
        application,
        path,
        headers=ORIGIN_HEADERS,
        subprotocols=subprotocols,
    )


def test_valid_human_jwt_connects_and_socket_is_read_only(super_admin_user):
    audit_count = AuditLog.objects.count()
    async def scenario():
        socket = communicator(access_token(super_admin_user))
        assert await socket.connect() == (True, "sflms.jwt")
        assert await socket.receive_json_from() == {
            "type": "security.connection.ready",
            "version": 1,
        }
        await socket.send_json_to({"action": "subscribe", "facility": "x"})
        error = await socket.receive_json_from()
        assert error["type"] == "security.error"
        assert error["error"]["code"] == "read_only"
        await socket.disconnect()

    async_to_sync(scenario)()
    assert AuditLog.objects.count() == audit_count


@pytest.mark.parametrize("credential_kind", ["missing", "invalid", "expired", "query", "aikey"])
def test_invalid_or_nonhuman_websocket_credentials_are_rejected(
    super_admin_user, credential_kind
):
    token = AccessToken.for_user(super_admin_user)
    path = "/ws/security/events/"
    offered_token = None
    if credential_kind == "invalid":
        offered_token = "not-a-jwt"
    elif credential_kind == "expired":
        token.set_exp(from_time=timezone.now(), lifetime=timedelta(seconds=-1))
        offered_token = str(token)
    elif credential_kind == "query":
        path = f"{path}?token={token}"
    elif credential_kind == "aikey":
        offered_token = "AIKey-machine-secret"

    async def scenario():
        socket = communicator(offered_token, path=path)
        assert await socket.connect() == (False, 4401)

    async_to_sync(scenario)()


def test_inactive_user_and_unauthorized_roles_are_rejected(
    super_admin_user, role_construction_manager, role_operations_manager
):
    inactive_token = access_token(super_admin_user)
    super_admin_user.status = User.STATUS_INACTIVE
    super_admin_user.save(update_fields=["status", "updated_at"])
    construction_user = make_user(role_construction_manager, "construction")
    operations_user = make_user(role_operations_manager, "operations")

    async def scenario():
        for token, code in (
            (inactive_token, 4401),
            (access_token(construction_user), 4403),
            (access_token(operations_user), 4403),
        ):
            socket = communicator(token)
            assert await socket.connect() == (False, code)

    async_to_sync(scenario)()


def test_facility_scope_super_admin_and_multi_facility_delivery(
    super_admin_user, role_security_officer
):
    facility_a, camera_a = make_camera(super_admin_user, "scope-a")
    _, camera_b = make_camera(super_admin_user, "scope-b")
    assigned = make_user(role_security_officer, "assigned")
    unassigned = make_user(role_security_officer, "unassigned")
    for facility in (facility_a, camera_b.facility):
        FacilityAssignment.objects.create(
            facility=facility,
            user=assigned,
            role_type=FacilityAssignment.RoleType.SECURITY_OFFICER,
            created_by=super_admin_user,
        )
    event_a = make_event(super_admin_user, camera_a)
    event_b = make_event(super_admin_user, camera_b)

    async def connect(user):
        socket = communicator(access_token(user))
        assert (await socket.connect())[0] is True
        await socket.receive_json_from()
        return socket

    async def scenario():
        admin_socket = await connect(super_admin_user)
        assigned_socket = await connect(assigned)
        unassigned_socket = await connect(unassigned)
        for event in (event_a, event_b):
            await sync_to_async(broadcast_camera_event_created)(event.pk)
            assert (await admin_socket.receive_json_from())["event"]["id"] == str(event.pk)
            assert (await assigned_socket.receive_json_from())["event"]["id"] == str(event.pk)
            assert await unassigned_socket.receive_nothing(timeout=0.1)
        for socket in (admin_socket, assigned_socket, unassigned_socket):
            await socket.disconnect()

    async_to_sync(scenario)()


def test_assignment_removed_before_broadcast_prevents_delivery(
    super_admin_user, role_security_officer
):
    facility, camera = make_camera(super_admin_user, "assignment-change")
    officer = make_user(role_security_officer, "assignment-change")
    assignment = FacilityAssignment.objects.create(
        facility=facility,
        user=officer,
        role_type=FacilityAssignment.RoleType.SECURITY_OFFICER,
        created_by=super_admin_user,
    )
    event = make_event(super_admin_user, camera)

    async def scenario():
        socket = communicator(access_token(officer))
        assert (await socket.connect())[0] is True
        await socket.receive_json_from()
        assignment.is_active = False
        await sync_to_async(assignment.save)(update_fields=["is_active", "updated_at"])
        await sync_to_async(broadcast_camera_event_created)(event.pk)
        assert await socket.receive_nothing(timeout=0.1)
        await socket.disconnect()

    async_to_sync(scenario)()


def test_camera_event_payload_is_bounded_and_snapshot_is_protected_reference(
    super_admin_user
):
    _, camera = make_camera(super_admin_user, "payload")
    event = make_event(super_admin_user, camera, event_type="vehicle_entry", authorized=False)
    event.snapshot_path = f"security/camera-events/{camera.facility_id}/{camera.pk}/snapshot.jpg"
    payload = camera_event_created_contract(event)
    serialized = json.dumps(payload).lower()
    assert payload["type"] == "security.camera_event.created"
    assert payload["version"] == 1
    assert payload["event"]["snapshot"] == {
        "available": True,
        "download_path": f"/api/v1/camera-events/{event.pk}/snapshot/",
    }
    assert payload["security_alert"]["alert_type"] == "vehicle"
    assert payload["security_alert"]["severity"] == "high"
    for forbidden in (
        "secret_hash", "authorization_header", "request_body", "ingestion_credential",
        "bbox", "base64", "security/camera-events/", "http://", "https://",
    ):
        assert forbidden not in serialized


def test_authorized_vehicle_event_has_no_alert_but_is_broadcastable(super_admin_user):
    _, camera = make_camera(super_admin_user, "authorized")
    event = make_event(
        super_admin_user, camera, event_type="vehicle_entry", authorized=True
    )
    payload = camera_event_created_contract(event)
    assert payload["event"]["authorized"] is True
    assert payload["event"]["security_alert_id"] is None
    assert payload["security_alert"] is None


@pytest.mark.parametrize(
    "event_type,alert_type,severity",
    [
        ("fire_alert", "fire", "critical"),
        ("smoke_alert", "smoke", "critical"),
        ("intrusion_alert", "intrusion", "high"),
        ("tamper_alert", "tamper", "critical"),
    ],
)
def test_alert_bearing_live_payload_preserves_persisted_mapping(
    super_admin_user, event_type, alert_type, severity
):
    _, camera = make_camera(super_admin_user, f"mapping-{event_type}")
    event = make_event(super_admin_user, camera, event_type=event_type)
    payload = camera_event_created_contract(event)
    assert payload["security_alert"]["alert_type"] == alert_type
    assert payload["security_alert"]["severity"] == severity


def test_security_alert_update_contract_is_bounded(super_admin_user):
    _, camera = make_camera(super_admin_user, "alert-update-payload")
    alert = make_event(super_admin_user, camera).security_alert
    alert.status = SecurityAlert.Status.REVIEWED
    payload = security_alert_updated_contract(alert)
    assert payload["type"] == "security.alert.updated"
    assert payload["version"] == 1
    assert payload["alert"]["event_id"] is not None
    assert "review_notes" not in payload["alert"]


def test_commit_broadcasts_and_rollback_does_not():
    event_id = uuid.uuid4()
    with patch("apps.security.realtime.broadcast_camera_event_created") as broadcast:
        with transaction.atomic():
            schedule_camera_event_created_broadcast(event_id)
            broadcast.assert_not_called()
        broadcast.assert_called_once_with(event_id)
    with patch("apps.security.realtime.broadcast_camera_event_created") as broadcast:
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                schedule_camera_event_created_broadcast(event_id)
                raise RuntimeError("rollback")
        broadcast.assert_not_called()


def test_idempotent_create_broadcasts_once_and_conflict_does_not(super_admin_user):
    _, camera = make_camera(super_admin_user, "idempotency")
    credential = make_machine(super_admin_user, camera)
    source_event_id = uuid.uuid4()
    data = {"event_type": "fire_alert", "object_class": "fire", "detected_at": timezone.now()}
    with patch("apps.security.realtime.broadcast_camera_event_created") as broadcast:
        first, created = create_camera_event(
            credential=credential, source_event_id=source_event_id,
            camera_id=camera.pk, data=dict(data),
        )
        retry, retry_created = create_camera_event(
            credential=credential, source_event_id=source_event_id,
            camera_id=camera.pk, data=dict(data),
        )
        assert created is True and retry_created is False and first.pk == retry.pk
        broadcast.assert_called_once_with(first.pk)
        with pytest.raises(CameraEventConflict):
            create_camera_event(
                credential=credential, source_event_id=source_event_id,
                camera_id=camera.pk, data={**data, "confidence": "0.500000"},
            )
        broadcast.assert_called_once_with(first.pk)


def test_patch_does_not_broadcast_or_create_alert_or_notification(super_admin_user):
    _, camera = make_camera(super_admin_user, "patch")
    credential = make_machine(super_admin_user, camera)
    with patch("apps.security.realtime.broadcast_camera_event_created"):
        event, _ = create_camera_event(
            credential=credential, source_event_id=uuid.uuid4(), camera_id=camera.pk,
            data={"event_type": "fire_alert", "object_class": "fire", "detected_at": timezone.now()},
        )
    alert_id = event.security_alert_id
    notification_count = Notification.objects.count()
    with patch("apps.security.realtime.broadcast_camera_event_created") as created_broadcast, patch(
        "apps.security.realtime.broadcast_security_alert_updated"
    ) as alert_broadcast:
        update_camera_event(
            event_id=event.pk, credential=credential, changes={"confidence": "0.900000"}
        )
        created_broadcast.assert_not_called()
        alert_broadcast.assert_not_called()
    event.refresh_from_db()
    assert event.security_alert_id == alert_id
    assert Notification.objects.count() == notification_count


def test_human_alert_lifecycle_broadcasts_only_successful_changes(super_admin_user):
    _, camera = make_camera(super_admin_user, "alert-lifecycle")
    alert = make_event(super_admin_user, camera).security_alert
    with patch("apps.security.realtime.broadcast_security_alert_updated") as broadcast:
        reviewed = review_security_alert(alert_id=alert.pk, actor=super_admin_user, notes="Confirmed")
        broadcast.assert_called_once_with(alert.pk)
        broadcast.reset_mock()
        dismissed = dismiss_security_alert(
            alert_id=alert.pk, actor=super_admin_user, reason="False positive"
        )
        broadcast.assert_called_once_with(alert.pk)
        broadcast.reset_mock()
        with pytest.raises(ValidationError):
            dismiss_security_alert(alert_id=alert.pk, actor=super_admin_user, reason="Again")
        broadcast.assert_not_called()
    assert reviewed.status == SecurityAlert.Status.REVIEWED
    assert dismissed.status == SecurityAlert.Status.DISMISSED


def test_alert_conversion_broadcasts_updated_state(super_admin_user):
    _, camera = make_camera(super_admin_user, "alert-convert")
    alert = make_event(super_admin_user, camera).security_alert
    review_security_alert(alert_id=alert.pk, actor=super_admin_user, notes="Confirmed")
    with patch("apps.security.realtime.broadcast_security_alert_updated") as broadcast:
        incident = convert_alert_to_incident(
            alert_id=alert.pk,
            actor=super_admin_user,
            incident_type="fire",
            description="Confirmed fire response",
        )
        broadcast.assert_called_once_with(alert.pk)
    alert.refresh_from_db()
    assert incident.alert_id == alert.pk
    assert alert.status == SecurityAlert.Status.CONVERTED


def test_route_and_asgi_application_load():
    assert application is not None


def test_redis_channel_layer_round_trip():
    if connection.settings_dict["ENGINE"].endswith("sqlite3"):
        pytest.skip("Redis integration runs with the Docker development settings.")
    channel_layer = get_channel_layer()
    assert channel_layer.__class__.__module__.startswith("channels_redis")

    async def scenario():
        channel = await channel_layer.new_channel()
        group = security_user_group(uuid.uuid4())
        await channel_layer.group_add(group, channel)
        message = {"type": "security.message", "payload": {"version": 1}}
        await channel_layer.group_send(group, message)
        assert await channel_layer.receive(channel) == message
        await channel_layer.group_discard(group, channel)

    async_to_sync(scenario)()
