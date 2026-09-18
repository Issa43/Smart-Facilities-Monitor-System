import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.urls import reverse
from django.utils import timezone

from apps.attachments.storage import get_protected_storage
from apps.audit.models import AuditLog
from apps.facilities.models import Facility, FacilityAssignment
from apps.notifications.models import Notification
from apps.security.camera_events import create_camera_event, update_camera_event
from apps.security.machine_credentials import create_ai_ingestion_credential
from apps.security.models import (
    AIIngestionCameraScope,
    AIIngestionCredential,
    AuthorizedVehicle,
    Camera,
    CameraROI,
    CameraEvent,
    Incident,
    SecurityAlert,
    VirtualLine,
)
from apps.users.models import Role, User


pytestmark = pytest.mark.django_db


def create_facility_camera(actor, suffix):
    facility = Facility.objects.create(
        name=f"Event Facility {suffix}",
        type=Facility.Type.INDUSTRIAL,
        location="Riyadh",
        created_by=actor,
    )
    camera = Camera.objects.create(
        facility=facility,
        code=f"EVENT-CAM-{suffix}",
        name=f"Event Camera {suffix}",
        zone="North Gate",
        status=Camera.Status.ONLINE,
        created_by=actor,
    )
    return facility, camera


def create_machine(actor, camera, suffix="primary"):
    return create_ai_ingestion_credential(
        name=f"Event machine {suffix}",
        actor=actor,
        cameras=[camera],
        expires_at=timezone.now() + timedelta(days=30),
    )


def machine_headers(credential, secret):
    return {"HTTP_AUTHORIZATION": f"AIKey {credential.key_id}:{secret}"}


def payload_for(camera, event_type, **overrides):
    roi = CameraROI.all_objects.filter(camera=camera).first()
    if roi is None:
        roi = CameraROI.objects.create(
            camera=camera,
            identifier="primary-zone",
            name="Primary zone",
            polygon=[
                {"x": 0, "y": 0},
                {"x": 100, "y": 0},
                {"x": 100, "y": 100},
            ],
            created_by=camera.created_by,
        )
    if not VirtualLine.all_objects.filter(camera=camera).exists():
        VirtualLine.objects.create(
            camera=camera,
            line_start={"x": 10, "y": 10},
            line_end={"x": 90, "y": 10},
            created_by=camera.created_by,
        )
    snapshot_key = (
        f"security/camera-events/{camera.facility_id}/{camera.pk}/"
        f"{uuid.uuid4().hex}.jpg"
    )
    get_protected_storage().save(
        snapshot_key,
        ContentFile(b"\xff\xd8\xff\xe0camera-event-image"),
    )
    payload = {
        "event_type": event_type,
        "camera_id": str(camera.pk),
        "source_event_id": str(uuid.uuid4()),
        "confidence": "0.875000",
        "detected_at": timezone.now().isoformat(),
        "bbox": {"x1": 10, "y1": 20, "x2": 100, "y2": 200},
        "confirmed_at": timezone.now().isoformat(),
        "duration_seconds": "3.000",
        "snapshot_path": snapshot_key,
    }
    if event_type == CameraEvent.EventType.FIRE_ALERT:
        payload.update({"class": "fire", "roi_id": str(roi.pk), "track_id": "track-fire"})
    elif event_type == CameraEvent.EventType.SMOKE_ALERT:
        payload.update({"class": "smoke", "roi_id": str(roi.pk), "track_id": "track-smoke"})
    elif event_type == CameraEvent.EventType.INTRUSION_ALERT:
        payload.update(
            {
                "class": "person",
                "roi_id": str(roi.pk),
                "track_id": "track-intrusion",
                "entered_roi_at": payload["detected_at"],
                "time_restricted": True,
            }
        )
    elif event_type in {
        CameraEvent.EventType.VEHICLE_ENTRY,
        CameraEvent.EventType.VEHICLE_EXIT,
    }:
        payload = {
            "event_type": event_type,
            "camera_id": str(camera.pk),
            "source_event_id": payload["source_event_id"],
            "detected_at": payload["detected_at"],
            "track_id": "track-vehicle",
            "plate_number": "ABC-1234",
            "plate_confidence": "0.910000",
            "ocr_confidence": "0.820000",
            "vehicle_type": "car",
            "vehicle_confidence": "0.930000",
            "direction": (
                "entry"
                if event_type == CameraEvent.EventType.VEHICLE_ENTRY
                else "exit"
            ),
            "authorized": False,
            "bbox_plate": {"x1": 20, "y1": 30, "x2": 50, "y2": 60},
            "bbox_vehicle": {"x1": 10, "y1": 20, "x2": 100, "y2": 200},
            "crossing_centroid": {"x": 55, "y": 70},
            "snapshot_path": snapshot_key,
        }
    elif event_type == CameraEvent.EventType.TAMPER_ALERT:
        payload = {
            "event_type": event_type,
            "camera_id": str(camera.pk),
            "source_event_id": payload["source_event_id"],
            "confidence": payload["confidence"],
            "detected_at": payload["detected_at"],
            "snapshot_path": snapshot_key,
            "tamper_type": CameraEvent.TamperType.CAMERA_COVERED,
        }
    payload.update(overrides)
    return payload


@pytest.fixture
def event_context(super_admin_user):
    facility, camera = create_facility_camera(super_admin_user, "primary")
    credential, secret = create_machine(super_admin_user, camera)
    return facility, camera, credential, secret


@pytest.mark.parametrize(
    "event_type,expected_alert_type,expected_severity",
    [
        ("fire_alert", "fire", "critical"),
        ("smoke_alert", "smoke", "critical"),
        ("intrusion_alert", "intrusion", "high"),
        ("vehicle_entry", "vehicle", "high"),
        ("vehicle_exit", "vehicle", "high"),
        ("tamper_alert", "tamper", "critical"),
    ],
)
def test_all_final_event_types_create_with_server_owned_alert_mapping(
    api_client,
    event_context,
    event_type,
    expected_alert_type,
    expected_severity,
):
    _, camera, credential, secret = event_context
    response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, event_type),
        format="json",
        **machine_headers(credential, secret),
    )

    assert response.status_code == 201, response.data
    event = CameraEvent.objects.get(pk=response.data["id"])
    assert event.security_alert.alert_type == expected_alert_type
    assert event.security_alert.severity_level == expected_severity
    assert event.security_alert.facility_id == camera.facility_id
    assert event.security_alert.source == SecurityAlert.Source.AI_DETECTION
    assert event.security_alert.created_by_id is None
    assert event.ingestion_credential_id == credential.pk
    assert Incident.objects.count() == 0


@pytest.mark.parametrize("event_type", ["vehicle_entry", "vehicle_exit"])
def test_authorized_vehicle_records_event_without_alert(
    api_client, event_context, event_type
):
    _, camera, credential, secret = event_context
    AuthorizedVehicle.objects.create(
        plate_number="ABC-1234",
        responsible_name="Authorized driver",
        created_by=camera.created_by,
    )
    response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, event_type, authorized=True),
        format="json",
        **machine_headers(credential, secret),
    )
    assert response.status_code == 201
    assert response.data["status"] == "recorded"
    assert response.data["security_alert_id"] is None
    assert SecurityAlert.objects.count() == 0


def test_vehicle_authorized_flag_must_match_server_registry(api_client, event_context):
    _, camera, credential, secret = event_context
    AuthorizedVehicle.objects.create(
        plate_number="ABC-1234",
        responsible_name="Authorized driver",
        created_by=camera.created_by,
    )
    response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, "vehicle_entry", authorized=False),
        format="json",
        **machine_headers(credential, secret),
    )
    assert response.status_code == 400
    assert "authorized" in response.data["error"]["details"]
    assert CameraEvent.objects.count() == 0


def test_post_is_idempotent_and_conflicting_retry_is_409(api_client, event_context):
    _, camera, credential, secret = event_context
    payload = payload_for(camera, "fire_alert")
    url = reverse("api_v1:camera-event-list")

    first = api_client.post(url, payload, format="json", **machine_headers(credential, secret))
    retry = api_client.post(url, payload, format="json", **machine_headers(credential, secret))
    conflict_payload = {**payload, "confidence": "0.500000"}
    conflict = api_client.post(
        url,
        conflict_payload,
        format="json",
        **machine_headers(credential, secret),
    )

    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.data["id"] == first.data["id"]
    assert conflict.status_code == 409
    assert CameraEvent.objects.count() == 1
    assert SecurityAlert.objects.count() == 1
    assert AuditLog.objects.filter(action="camera_event.created").count() == 1
    assert AuditLog.objects.filter(
        action="security_alert.created_from_camera_event"
    ).count() == 1


@pytest.mark.parametrize(
    "header",
    [None, "AIKey malformed", "AIKey missing:wrong", "Bearer not-a-jwt"],
)
def test_invalid_or_missing_machine_auth_cannot_post(
    api_client, event_context, header
):
    _, camera, _, _ = event_context
    kwargs = {"HTTP_AUTHORIZATION": header} if header else {}
    response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, "fire_alert"),
        format="json",
        **kwargs,
    )
    assert response.status_code in {401, 403}
    assert CameraEvent.objects.count() == 0


def test_human_jwt_identity_cannot_post(api_client, super_admin_user, event_context):
    _, camera, _, _ = event_context
    api_client.force_authenticate(super_admin_user)
    response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, "fire_alert"),
        format="json",
    )
    assert response.status_code == 403


def test_machine_and_unauthenticated_callers_cannot_read(api_client, event_context):
    _, _, credential, secret = event_context
    url = reverse("api_v1:camera-event-list")
    assert api_client.get(url).status_code == 401
    assert api_client.get(url, **machine_headers(credential, secret)).status_code == 401


@pytest.mark.parametrize("state", ["revoked", "expired", "inactive"])
def test_unusable_machine_credentials_cannot_post(
    api_client, super_admin_user, event_context, state
):
    _, camera, credential, secret = event_context
    if state == "revoked":
        credential.revoked_at = timezone.now()
        credential.revoked_by = super_admin_user
        credential.is_active = False
        credential.save(update_fields=["revoked_at", "revoked_by", "is_active"])
    elif state == "expired":
        credential.expires_at = timezone.now() - timedelta(seconds=1)
        credential.save(update_fields=["expires_at"])
    else:
        credential.is_active = False
        credential.save(update_fields=["is_active"])

    response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, "fire_alert"),
        format="json",
        **machine_headers(credential, secret),
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "scope_state,expected_status",
    [("scoped", 201), ("unscoped", 400), ("inactive_scope", 400)],
)
def test_camera_scope_is_enforced(
    api_client, super_admin_user, event_context, scope_state, expected_status
):
    _, scoped_camera, credential, secret = event_context
    if scope_state == "scoped":
        camera = scoped_camera
    else:
        _, camera = create_facility_camera(super_admin_user, scope_state)
        if scope_state == "inactive_scope":
            AIIngestionCameraScope.objects.create(
                credential=credential,
                camera=camera,
                created_by=super_admin_user,
                is_active=False,
            )
    response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, "fire_alert"),
        format="json",
        **machine_headers(credential, secret),
    )
    assert response.status_code == expected_status


@pytest.mark.parametrize("inactive_target", ["camera", "facility"])
def test_inactive_camera_or_facility_is_rejected(
    api_client, event_context, inactive_target
):
    facility, camera, credential, secret = event_context
    target = camera if inactive_target == "camera" else facility
    target.is_active = False
    target.save(update_fields=["is_active"])
    response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, "fire_alert"),
        format="json",
        **machine_headers(credential, secret),
    )
    assert response.status_code == 400


@pytest.mark.parametrize("field", ["facility", "facility_id", "severity", "type_mismatch_flag"])
def test_machine_cannot_supply_server_owned_or_future_fields(
    api_client, event_context, field
):
    facility, camera, credential, secret = event_context
    payload = payload_for(camera, "fire_alert")
    payload[field] = str(facility.pk) if field.startswith("facility") else "critical"
    response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload,
        format="json",
        **machine_headers(credential, secret),
    )
    assert response.status_code == 400
    assert field in response.data["error"]["details"]


@pytest.mark.parametrize(
    "event_type,required_fields",
    [
        (
            CameraEvent.EventType.FIRE_ALERT,
            {
                "roi_id",
                "track_id",
                "class",
                "confidence",
                "bbox",
                "confirmed_at",
                "duration_seconds",
                "snapshot_path",
            },
        ),
        (
            CameraEvent.EventType.SMOKE_ALERT,
            {
                "roi_id",
                "track_id",
                "class",
                "confidence",
                "bbox",
                "confirmed_at",
                "duration_seconds",
                "snapshot_path",
            },
        ),
        (
            CameraEvent.EventType.INTRUSION_ALERT,
            {
                "roi_id",
                "track_id",
                "class",
                "confidence",
                "bbox",
                "entered_roi_at",
                "confirmed_at",
                "duration_seconds",
                "time_restricted",
                "snapshot_path",
            },
        ),
        (
            CameraEvent.EventType.VEHICLE_ENTRY,
            {
                "track_id",
                "plate_number",
                "plate_confidence",
                "ocr_confidence",
                "vehicle_type",
                "vehicle_confidence",
                "direction",
                "crossing_centroid",
                "authorized",
                "bbox_plate",
                "bbox_vehicle",
                "snapshot_path",
            },
        ),
        (
            CameraEvent.EventType.VEHICLE_EXIT,
            {
                "track_id",
                "plate_number",
                "plate_confidence",
                "ocr_confidence",
                "vehicle_type",
                "vehicle_confidence",
                "direction",
                "crossing_centroid",
                "authorized",
                "bbox_plate",
                "bbox_vehicle",
                "snapshot_path",
            },
        ),
        (
            CameraEvent.EventType.TAMPER_ALERT,
            {"tamper_type", "confidence"},
        ),
    ],
)
def test_event_type_required_fields_are_enforced(
    api_client, event_context, event_type, required_fields
):
    _, camera, credential, secret = event_context
    url = reverse("api_v1:camera-event-list")
    for field in required_fields:
        payload = payload_for(camera, event_type)
        payload.pop(field)
        response = api_client.post(
            url,
            payload,
            format="json",
            **machine_headers(credential, secret),
        )
        assert response.status_code == 400, (event_type, field, response.data)
        assert field in response.data["error"]["details"]


@pytest.mark.parametrize("field", ["camera_id", "source_event_id"])
def test_common_external_identity_fields_are_required(
    api_client, event_context, field
):
    _, camera, credential, secret = event_context
    payload = payload_for(camera, "fire_alert")
    payload.pop(field)
    response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload,
        format="json",
        **machine_headers(credential, secret),
    )
    assert response.status_code == 400
    assert field in response.data["error"]["details"]


@pytest.mark.parametrize(
    "legacy_field,value",
    [
        ("camera", str(uuid.uuid4())),
        ("object_class", "fire"),
    ],
)
def test_legacy_internal_field_aliases_are_rejected(
    api_client, event_context, legacy_field, value
):
    _, camera, credential, secret = event_context
    payload = payload_for(camera, "fire_alert")
    payload[legacy_field] = value
    response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload,
        format="json",
        **machine_headers(credential, secret),
    )
    assert response.status_code == 400
    assert legacy_field in response.data["error"]["details"]


def test_intrusion_requires_restricted_time_true(api_client, event_context):
    _, camera, credential, secret = event_context
    response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, "intrusion_alert", time_restricted=False),
        format="json",
        **machine_headers(credential, secret),
    )
    assert response.status_code == 400
    assert "time_restricted" in response.data["error"]["details"]


def test_vehicle_requires_active_camera_virtual_line(api_client, event_context):
    _, camera, credential, secret = event_context
    payload = payload_for(camera, "vehicle_entry")
    VirtualLine.objects.filter(camera=camera).update(is_active=False)
    response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload,
        format="json",
        **machine_headers(credential, secret),
    )
    assert response.status_code == 400
    assert "camera_id" in response.data["error"]["details"]


def test_vehicle_plate_is_minimally_normalized(api_client, event_context):
    _, camera, credential, secret = event_context
    response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, "vehicle_entry", plate_number="  abc-1234  "),
        format="json",
        **machine_headers(credential, secret),
    )
    assert response.status_code == 201, response.data
    assert response.data["plate_number"] == "ABC-1234"


@pytest.mark.parametrize(
    "field,value",
    [
        ("event_type", "unknown"),
        ("confidence", "1.100000"),
        ("confidence", "-0.100000"),
        ("confidence", "NaN"),
        ("bbox", [1, 2, 3, 4]),
        ("bbox", {"x1": -1, "y1": 0, "x2": 2, "y2": 3}),
        ("bbox", {"x1": 3, "y1": 0, "x2": 2, "y2": 3}),
        ("vehicle_type", "spaceship"),
        ("direction", "sideways"),
        ("tamper_type", "lens_missing"),
    ],
)
def test_invalid_contract_values_are_rejected(
    api_client, event_context, field, value
):
    _, camera, credential, secret = event_context
    event_type = "vehicle_entry" if field in {"vehicle_type", "direction"} else "fire_alert"
    if field == "tamper_type":
        event_type = "tamper_alert"
    payload = payload_for(camera, event_type)
    payload[field] = value
    response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload,
        format="json",
        **machine_headers(credential, secret),
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "event_type,direction", [("vehicle_entry", "exit"), ("vehicle_exit", "entry")]
)
def test_vehicle_direction_must_match_event_type(
    api_client, event_context, event_type, direction
):
    _, camera, credential, secret = event_context
    response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, event_type, direction=direction),
        format="json",
        **machine_headers(credential, secret),
    )
    assert response.status_code == 400


def test_tamper_needs_neither_track_nor_roi_and_anpr_confidences_stay_separate(
    api_client, event_context
):
    _, camera, credential, secret = event_context
    tamper = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, "tamper_alert"),
        format="json",
        **machine_headers(credential, secret),
    )
    vehicle = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, "vehicle_entry"),
        format="json",
        **machine_headers(credential, secret),
    )
    assert tamper.status_code == 201
    assert tamper.data["track_id"] is None
    assert tamper.data["entered_roi_at"] is None
    assert vehicle.data["plate_confidence"] == "0.910000"
    assert vehicle.data["ocr_confidence"] == "0.820000"


def test_patch_only_allows_continued_observation_fields(api_client, event_context):
    _, camera, credential, secret = event_context
    created = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, "fire_alert", track_id="track-1"),
        format="json",
        **machine_headers(credential, secret),
    )
    event_id = created.data["id"]
    alert_id = created.data["security_alert_id"]
    audit_count = AuditLog.objects.filter(action="camera_event.created").count()
    notification_count = Notification.objects.count()

    patched = api_client.patch(
        reverse("api_v1:camera-event-detail", kwargs={"pk": event_id}),
        {
            "confidence": "0.950000",
            "duration_seconds": "12.500",
            "confirmed_at": timezone.now().isoformat(),
            "bbox": {"x1": 11, "y1": 21, "x2": 101, "y2": 201},
        },
        format="json",
        **machine_headers(credential, secret),
    )
    assert patched.status_code == 200, patched.data
    assert patched.data["confidence"] == "0.950000"
    assert patched.data["security_alert_id"] == alert_id
    assert SecurityAlert.objects.count() == 1
    assert Incident.objects.count() == 0
    assert Notification.objects.count() == notification_count
    assert AuditLog.objects.filter(action="camera_event.created").count() == audit_count


@pytest.mark.parametrize(
    "field,value",
    [
        ("event_type", "smoke_alert"),
        ("camera_id", str(uuid.uuid4())),
        ("source_event_id", str(uuid.uuid4())),
        ("track_id", "other"),
        ("authorized", True),
        ("direction", "exit"),
        ("plate_number", "OTHER"),
        ("tamper_type", "camera_moved"),
        ("security_alert", str(uuid.uuid4())),
    ],
)
def test_machine_patch_rejects_immutable_fields(
    api_client, event_context, field, value
):
    _, camera, credential, secret = event_context
    created = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, "fire_alert", track_id="track-immutable"),
        format="json",
        **machine_headers(credential, secret),
    )
    response = api_client.patch(
        reverse("api_v1:camera-event-detail", kwargs={"pk": created.data["id"]}),
        {field: value},
        format="json",
        **machine_headers(credential, secret),
    )
    assert response.status_code == 400
    assert field in response.data["error"]["details"]


def test_only_originating_scoped_machine_can_patch(
    api_client, super_admin_user, event_context
):
    _, camera, credential, secret = event_context
    other, other_secret = create_machine(super_admin_user, camera, "other")
    created = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, "fire_alert"),
        format="json",
        **machine_headers(credential, secret),
    )
    url = reverse("api_v1:camera-event-detail", kwargs={"pk": created.data["id"]})
    other_response = api_client.patch(
        url,
        {"confidence": "0.500000"},
        format="json",
        **machine_headers(other, other_secret),
    )
    api_client.force_authenticate(super_admin_user)
    human_response = api_client.patch(url, {"confidence": "0.500000"}, format="json")
    assert other_response.status_code == 404
    assert human_response.status_code == 403


def create_role_user(role, suffix):
    return User.objects.create_user(
        email=f"event-{suffix}@sflms.test",
        username=f"event-{suffix}",
        full_name=f"Event {suffix}",
        password="StrongPass123!",
        role=role,
    )


def test_human_reads_follow_security_facility_scope(
    api_client,
    super_admin_user,
    role_security_officer,
    role_operations_manager,
    role_construction_manager,
):
    facility_a, camera_a = create_facility_camera(super_admin_user, "read-a")
    _, camera_b = create_facility_camera(super_admin_user, "read-b")
    credential_a, _ = create_machine(super_admin_user, camera_a, "read-a")
    credential_b, _ = create_machine(super_admin_user, camera_b, "read-b")
    data_a = payload_for(camera_a, "fire_alert")
    data_b = payload_for(camera_b, "fire_alert")
    for credential, camera, payload in (
        (credential_a, camera_a, data_a),
        (credential_b, camera_b, data_b),
    ):
        values = dict(payload)
        values.pop("camera_id")
        source_event_id = values.pop("source_event_id")
        from api.v1.camera_events.serializers import CameraEventCreateSerializer

        serializer = CameraEventCreateSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        validated = dict(serializer.validated_data)
        validated.pop("camera")
        validated.pop("source_event_id")
        create_camera_event(
            credential=credential,
            source_event_id=source_event_id,
            camera_id=camera.pk,
            data=validated,
        )

    officer = create_role_user(role_security_officer, "officer")
    FacilityAssignment.objects.create(
        facility=facility_a,
        user=officer,
        role_type=FacilityAssignment.RoleType.SECURITY_OFFICER,
        created_by=super_admin_user,
    )
    api_client.force_authenticate(officer)
    scoped = api_client.get(reverse("api_v1:camera-event-list"))
    forbidden_detail = api_client.get(
        reverse(
            "api_v1:camera-event-detail",
            kwargs={"pk": CameraEvent.objects.get(camera=camera_b).pk},
        )
    )
    assert scoped.status_code == 200
    assert len(scoped.data["results"]) == 1
    assert forbidden_detail.status_code == 404

    api_client.force_authenticate(super_admin_user)
    assert api_client.get(reverse("api_v1:camera-event-list")).data["count"] == 2
    for role, suffix in (
        (role_operations_manager, "operations"),
        (role_construction_manager, "construction"),
    ):
        api_client.force_authenticate(create_role_user(role, suffix))
        assert api_client.get(reverse("api_v1:camera-event-list")).status_code == 403


@pytest.mark.parametrize(
    "bad_path",
    [
        "https://example.test/image.jpg",
        "/security/camera-events/image.jpg",
        "C:/security/camera-events/image.jpg",
        "security/camera-events/../image.jpg",
        r"security\camera-events\image.jpg",
    ],
)
def test_unsafe_snapshot_paths_are_rejected(
    api_client, event_context, bad_path
):
    _, camera, credential, secret = event_context
    response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, "fire_alert", snapshot_path=bad_path),
        format="json",
        **machine_headers(credential, secret),
    )
    assert response.status_code == 400
    assert "snapshot_path" in response.data["error"]["details"]


def test_snapshot_requires_exact_prefix_exists_and_is_never_exposed(
    api_client, event_context
):
    facility, camera, credential, secret = event_context
    missing = (
        f"security/camera-events/{facility.pk}/{camera.pk}/missing.jpg"
    )
    missing_response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, "fire_alert", snapshot_path=missing),
        format="json",
        **machine_headers(credential, secret),
    )
    assert missing_response.status_code == 400

    key = f"security/camera-events/{facility.pk}/{camera.pk}/{uuid.uuid4().hex}.jpg"
    storage = get_protected_storage()
    storage.save(key, ContentFile(b"\xff\xd8\xff\xe0camera-event-image"))
    try:
        response = api_client.post(
            reverse("api_v1:camera-event-list"),
            payload_for(camera, "fire_alert", snapshot_path=key),
            format="json",
            **machine_headers(credential, secret),
        )
        assert response.status_code == 201, response.data
        serialized = json.dumps(response.data)
        assert key not in serialized
        assert response.data["snapshot_available"] is True
        assert response.data["snapshot_download_url"].endswith("/snapshot/")
        event = CameraEvent.objects.get(pk=response.data["id"])
        assert not event.security_alert.snapshot_image

        api_client.force_authenticate(credential.created_by)
        download = api_client.get(response.data["snapshot_download_url"])
        assert download.status_code == 200
        alert_download = api_client.get(
            reverse(
                "api_v1:security-alert-snapshot",
                kwargs={"pk": event.security_alert_id},
            )
        )
        assert alert_download.status_code == 200
    finally:
        if storage.exists(key):
            storage.delete(key)


def test_wrong_snapshot_prefix_and_invalid_content_are_rejected(
    api_client, event_context
):
    facility, camera, credential, secret = event_context
    wrong = f"security/camera-events/{facility.pk}/{uuid.uuid4()}/image.jpg"
    response = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, "fire_alert", snapshot_path=wrong),
        format="json",
        **machine_headers(credential, secret),
    )
    assert response.status_code == 400

    key = f"security/camera-events/{facility.pk}/{camera.pk}/{uuid.uuid4().hex}.jpg"
    storage = get_protected_storage()
    storage.save(key, ContentFile(b"not-a-jpeg"))
    try:
        response = api_client.post(
            reverse("api_v1:camera-event-list"),
            payload_for(camera, "fire_alert", snapshot_path=key),
            format="json",
            **machine_headers(credential, secret),
        )
        assert response.status_code == 400
    finally:
        if storage.exists(key):
            storage.delete(key)


def test_status_projects_alert_workflow_without_event_status_field(
    api_client, super_admin_user, event_context
):
    _, camera, credential, secret = event_context
    AuthorizedVehicle.objects.create(
        plate_number="ABC-1234",
        responsible_name="Authorized driver",
        created_by=camera.created_by,
    )
    authorized = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, "vehicle_entry", authorized=True),
        format="json",
        **machine_headers(credential, secret),
    )
    alert_event = api_client.post(
        reverse("api_v1:camera-event-list"),
        payload_for(camera, "fire_alert"),
        format="json",
        **machine_headers(credential, secret),
    )
    alert = SecurityAlert.objects.get(pk=alert_event.data["security_alert_id"])
    alert.status = SecurityAlert.Status.REVIEWED
    alert.save(update_fields=["status"])
    api_client.force_authenticate(super_admin_user)
    detail = api_client.get(
        reverse("api_v1:camera-event-detail", kwargs={"pk": alert_event.data["id"]})
    )
    assert authorized.data["status"] == "recorded"
    assert detail.data["status"] == "reviewed"
    assert not any(field.name == "status" for field in CameraEvent._meta.fields)


def test_semantic_audits_are_once_and_exclude_sensitive_values(
    api_client, event_context
):
    _, camera, credential, secret = event_context
    payload = payload_for(camera, "fire_alert")
    url = reverse("api_v1:camera-event-list")
    first = api_client.post(url, payload, format="json", **machine_headers(credential, secret))
    api_client.post(url, payload, format="json", **machine_headers(credential, secret))
    api_client.patch(
        reverse("api_v1:camera-event-detail", kwargs={"pk": first.data["id"]}),
        {"confidence": "0.900000"},
        format="json",
        **machine_headers(credential, secret),
    )
    assert AuditLog.objects.filter(action="camera_event.created").count() == 1
    assert AuditLog.objects.filter(
        action="security_alert.created_from_camera_event"
    ).count() == 1
    semantic = json.dumps(
        list(
            AuditLog.objects.filter(
                action__in=[
                    "camera_event.created",
                    "security_alert.created_from_camera_event",
                ]
            ).values("before", "after", "entity_ref")
        )
    )
    assert secret not in semantic
    assert credential.secret_hash not in semantic
    assert "snapshot_path" not in semantic


def test_alert_failure_rolls_back_event(monkeypatch, event_context):
    _, camera, credential, _ = event_context
    payload = payload_for(camera, "fire_alert")
    from api.v1.camera_events.serializers import CameraEventCreateSerializer

    serializer = CameraEventCreateSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    data = dict(serializer.validated_data)
    camera_id = data.pop("camera")
    source_event_id = data.pop("source_event_id")

    def fail_alert(_event):
        raise IntegrityError("forced alert failure")

    monkeypatch.setattr("apps.security.camera_events._create_security_alert", fail_alert)
    with pytest.raises(Exception):
        create_camera_event(
            credential=credential,
            source_event_id=source_event_id,
            camera_id=camera_id,
            data=data,
        )
    assert CameraEvent.objects.count() == 0
    assert SecurityAlert.objects.count() == 0


def test_database_enforces_idempotency_and_one_to_one(event_context):
    _, camera, credential, _ = event_context
    source_id = uuid.uuid4()
    first = CameraEvent.objects.create(
        event_type="fire_alert",
        camera=camera,
        ingestion_credential=credential,
        source_event_id=source_id,
        object_class="fire",
        detected_at=timezone.now(),
        created_by=credential.principal,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        CameraEvent.objects.create(
            event_type="fire_alert",
            camera=camera,
            ingestion_credential=credential,
            source_event_id=source_id,
            object_class="fire",
            detected_at=timezone.now(),
        )
    alert = SecurityAlert.objects.create(
        facility=camera.facility,
        alert_type="fire",
        location=camera.zone,
        severity_level="critical",
        source="ai_detection",
    )
    first.security_alert = alert
    first.save(update_fields=["security_alert"])
    other = CameraEvent.objects.create(
        event_type="fire_alert",
        camera=camera,
        ingestion_credential=credential,
        source_event_id=uuid.uuid4(),
        object_class="fire",
        detected_at=timezone.now(),
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        other.security_alert = alert
        other.save(update_fields=["security_alert"])


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_post_creates_one_event_and_one_alert(
    super_admin_user,
):
    if connection.vendor == "sqlite":
        pytest.skip("True transaction race test requires the production PostgreSQL backend.")
    _, camera = create_facility_camera(super_admin_user, "race")
    credential, _ = create_machine(super_admin_user, camera, "race")
    source_event_id = uuid.uuid4()
    data = {
        "event_type": "fire_alert",
        "track_id": None,
        "confidence": Decimal("0.800000"),
        "object_class": "fire",
        "detected_at": timezone.now(),
        "confirmed_at": None,
        "duration_seconds": None,
        "snapshot_path": None,
        "bbox": None,
        "bbox_plate": None,
        "bbox_vehicle": None,
        "crossing_centroid": None,
        "entered_roi_at": None,
        "time_restricted": None,
        "plate_number": None,
        "plate_confidence": None,
        "ocr_confidence": None,
        "vehicle_type": None,
        "vehicle_confidence": None,
        "direction": None,
        "authorized": None,
        "tamper_type": None,
    }

    def submit():
        close_old_connections()
        thread_credential = AIIngestionCredential.objects.get(pk=credential.pk)
        try:
            return create_camera_event(
                credential=thread_credential,
                source_event_id=source_event_id,
                camera_id=camera.pk,
                data=dict(data),
            )[1]
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        created_flags = list(pool.map(lambda _: submit(), range(2)))
    assert sorted(created_flags) == [False, True]
    assert CameraEvent.objects.filter(source_event_id=source_event_id).count() == 1
    assert SecurityAlert.objects.count() == 1
    assert AuditLog.objects.filter(action="camera_event.created").count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_patch_preserves_immutable_identity(super_admin_user):
    if connection.vendor == "sqlite":
        pytest.skip("True row-lock test requires the production PostgreSQL backend.")
    _, camera = create_facility_camera(super_admin_user, "patch-race")
    credential, _ = create_machine(super_admin_user, camera, "patch-race")
    event, _ = create_camera_event(
        credential=credential,
        source_event_id=uuid.uuid4(),
        camera_id=camera.pk,
        data={
            "event_type": "fire_alert",
            "object_class": "fire",
            "detected_at": timezone.now(),
        },
    )
    immutable = (event.event_type, event.camera_id, event.source_event_id)

    def patch(confidence):
        close_old_connections()
        thread_credential = AIIngestionCredential.objects.get(pk=credential.pk)
        try:
            update_camera_event(
                event_id=event.pk,
                credential=thread_credential,
                changes={"confidence": confidence},
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(patch, [Decimal("0.700000"), Decimal("0.900000")]))
    event.refresh_from_db()
    assert (event.event_type, event.camera_id, event.source_event_id) == immutable
    assert event.confidence in {Decimal("0.700000"), Decimal("0.900000")}
    assert SecurityAlert.objects.count() == 1
