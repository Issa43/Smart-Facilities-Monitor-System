import math
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import time, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.attachments.storage import get_protected_storage
from apps.facilities.models import Facility
from apps.security.configuration import enable_camera_ai_model
from apps.security.machine_credentials import create_ai_ingestion_credential
from apps.security.models import (
    AuthorizedVehicle,
    Camera,
    CameraAIModel,
    CameraEvent,
    CameraROI,
    RestrictedZoneSchedule,
    VirtualLine,
)
from apps.users.models import User


pytestmark = pytest.mark.django_db


TRIANGLE = [{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 50, "y": 80}]


def make_camera(actor, suffix):
    facility = Facility.objects.create(
        name=f"Configuration Facility {suffix}",
        type=Facility.Type.INDUSTRIAL,
        location="Riyadh",
        created_by=actor,
    )
    camera = Camera.objects.create(
        facility=facility,
        code=f"CFG-CAM-{suffix}",
        name=f"Configuration Camera {suffix}",
        zone="Gate",
        status=Camera.Status.ONLINE,
        created_by=actor,
    )
    return facility, camera


def make_machine(actor, cameras):
    return create_ai_ingestion_credential(
        name="Configuration reader",
        actor=actor,
        cameras=cameras,
        expires_at=timezone.now() + timedelta(days=30),
    )


def machine_headers(credential, secret):
    return {"HTTP_AUTHORIZATION": f"AIKey {credential.key_id}:{secret}"}


def results(response):
    return response.data.get("results", response.data)


def make_roi(camera, actor, identifier="restricted-zone"):
    return CameraROI.objects.create(
        camera=camera,
        identifier=identifier,
        name="Restricted zone",
        polygon=TRIANGLE,
        created_by=actor,
    )


def test_roi_human_crud_machine_scope_and_stable_camera_filter(
    api_client, super_admin_user
):
    _, camera_a = make_camera(super_admin_user, "roi-a")
    _, camera_b = make_camera(super_admin_user, "roi-b")
    credential, secret = make_machine(super_admin_user, [camera_a])
    api_client.force_authenticate(super_admin_user)

    created = api_client.post(
        reverse("api_v1:camera-roi-list"),
        {
            "camera": str(camera_a.pk),
            "identifier": "fire-zone",
            "name": "Fire zone",
            "polygon": TRIANGLE,
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    make_roi(camera_b, super_admin_user, "other-camera")

    api_client.force_authenticate(user=None)
    scoped = api_client.get(
        reverse("api_v1:camera-roi-list"),
        {"camera_id": str(camera_a.pk)},
        **machine_headers(credential, secret),
    )
    leaked = api_client.get(
        reverse("api_v1:camera-roi-list"),
        {"camera_id": str(camera_b.pk)},
        **machine_headers(credential, secret),
    )
    assert scoped.status_code == 200
    assert [row["id"] for row in results(scoped)] == [created.data["id"]]
    assert results(leaked) == []
    assert "facility" not in scoped.data and secret not in str(scoped.data)


@pytest.mark.parametrize(
    "polygon",
    [
        None,
        [],
        [{"x": 0, "y": 0}, {"x": 1, "y": 1}, {"x": 2, "y": 2}],
        [{"x": 0, "y": 0}, {"x": 1}, {"x": 1, "y": 2}],
        [{"x": -1, "y": 0}, {"x": 1, "y": 0}, {"x": 0, "y": 1}],
        [{"x": math.nan, "y": 0}, {"x": 1, "y": 0}, {"x": 0, "y": 1}],
        [{"x": math.inf, "y": 0}, {"x": 1, "y": 0}, {"x": 0, "y": 1}],
    ],
)
def test_roi_geometry_is_strict(super_admin_user, polygon):
    _, camera = make_camera(super_admin_user, f"geometry-{uuid.uuid4().hex[:6]}")
    roi = CameraROI(
        camera=camera,
        identifier="zone",
        name="Zone",
        polygon=polygon,
        created_by=super_admin_user,
    )
    with pytest.raises(ValidationError):
        roi.full_clean()


def test_roi_deactivation_preserves_historical_camera_event(
    super_admin_user,
):
    _, camera = make_camera(super_admin_user, "roi-history")
    credential, _ = make_machine(super_admin_user, [camera])
    roi = make_roi(camera, super_admin_user)
    event = CameraEvent.objects.create(
        event_type=CameraEvent.EventType.FIRE_ALERT,
        camera=camera,
        roi=roi,
        ingestion_credential=credential,
        source_event_id=uuid.uuid4(),
        object_class="fire",
        detected_at=timezone.now(),
        created_by=credential.principal,
    )
    roi.is_active = False
    roi.save(update_fields=["is_active", "updated_at"])
    event.refresh_from_db()
    assert event.roi_id == roi.pk
    assert event.roi.polygon == TRIANGLE


def test_camera_event_accepts_only_active_roi_for_its_authorized_camera(
    api_client, super_admin_user
):
    _, camera_a = make_camera(super_admin_user, "event-roi-a")
    _, camera_b = make_camera(super_admin_user, "event-roi-b")
    credential, secret = make_machine(super_admin_user, [camera_a])
    valid_roi = make_roi(camera_a, super_admin_user, "valid")
    foreign_roi = make_roi(camera_b, super_admin_user, "foreign")
    endpoint = reverse("api_v1:camera-event-list")

    def payload(roi):
        snapshot_key = (
            f"security/camera-events/{camera_a.facility_id}/{camera_a.pk}/"
            f"{uuid.uuid4().hex}.jpg"
        )
        get_protected_storage().save(
            snapshot_key,
            ContentFile(b"\xff\xd8\xff\xe0camera-event-image"),
        )
        return {
            "event_type": "fire_alert",
            "camera_id": str(camera_a.pk),
            "roi_id": str(roi.pk),
            "source_event_id": str(uuid.uuid4()),
            "class": "fire",
            "track_id": "roi-validation-track",
            "confidence": "0.900000",
            "bbox": {"x1": 0, "y1": 0, "x2": 10, "y2": 10},
            "detected_at": timezone.now().isoformat(),
            "confirmed_at": timezone.now().isoformat(),
            "duration_seconds": "2.000",
            "snapshot_path": snapshot_key,
        }

    accepted = api_client.post(
        endpoint,
        payload(valid_roi),
        format="json",
        **machine_headers(credential, secret),
    )
    rejected = api_client.post(
        endpoint,
        payload(foreign_roi),
        format="json",
        **machine_headers(credential, secret),
    )
    valid_roi.is_active = False
    valid_roi.save(update_fields=["is_active", "updated_at"])
    inactive = api_client.post(
        endpoint,
        payload(valid_roi),
        format="json",
        **machine_headers(credential, secret),
    )
    assert accepted.status_code == 201, accepted.data
    assert accepted.data["roi_id"] == str(valid_roi.pk)
    assert rejected.status_code == 400
    assert inactive.status_code == 400


@pytest.mark.parametrize(
    "values,crosses_midnight",
    [
        (
            {
                "always_restricted": True,
                "from_time": None,
                "to_time": None,
                "days_of_week": [],
                "timezone_name": "Asia/Riyadh",
            },
            False,
        ),
        (
            {
                "always_restricted": False,
                "from_time": time(8),
                "to_time": time(17),
                "days_of_week": [0, 1, 2, 3, 4],
                "timezone_name": "Asia/Riyadh",
            },
            False,
        ),
        (
            {
                "always_restricted": False,
                "from_time": time(22),
                "to_time": time(6),
                "days_of_week": [4, 5],
                "timezone_name": "America/Los_Angeles",
            },
            True,
        ),
    ],
)
def test_schedule_modes_timezone_and_overnight(
    super_admin_user, values, crosses_midnight
):
    _, camera = make_camera(super_admin_user, f"schedule-{uuid.uuid4().hex[:6]}")
    schedule = RestrictedZoneSchedule(
        roi=make_roi(camera, super_admin_user),
        created_by=super_admin_user,
        **values,
    )
    schedule.full_clean()
    assert schedule.crosses_midnight is crosses_midnight


@pytest.mark.parametrize(
    "changes",
    [
        {"timezone_name": "Not/A-Timezone"},
        {"days_of_week": [7]},
        {"days_of_week": [1, 1]},
        {"from_time": None},
        {"from_time": time(8), "to_time": time(8)},
    ],
)
def test_invalid_schedule_contract_is_rejected(super_admin_user, changes):
    _, camera = make_camera(super_admin_user, f"bad-schedule-{uuid.uuid4().hex[:6]}")
    values = {
        "roi": make_roi(camera, super_admin_user),
        "always_restricted": False,
        "from_time": time(8),
        "to_time": time(17),
        "days_of_week": [0, 1],
        "timezone_name": "Asia/Riyadh",
        "created_by": super_admin_user,
    }
    values.update(changes)
    with pytest.raises(ValidationError):
        RestrictedZoneSchedule(**values).full_clean()


def test_schedule_machine_read_is_roi_camera_scoped(api_client, super_admin_user):
    _, camera_a = make_camera(super_admin_user, "schedule-a")
    _, camera_b = make_camera(super_admin_user, "schedule-b")
    credential, secret = make_machine(super_admin_user, [camera_a])
    for camera in (camera_a, camera_b):
        RestrictedZoneSchedule.objects.create(
            roi=make_roi(camera, super_admin_user),
            always_restricted=True,
            timezone_name="Asia/Riyadh",
            created_by=super_admin_user,
        )
    response = api_client.get(
        reverse("api_v1:restricted-schedule-list"),
        **machine_headers(credential, secret),
    )
    assert response.status_code == 200
    assert {row["camera_id"] for row in results(response)} == {str(camera_a.pk)}


@pytest.mark.parametrize(
    "start,end",
    [
        ({"x": 1}, {"x": 2, "y": 2}),
        ({"x": 1, "y": 1}, {"x": 1, "y": 1}),
        ({"x": -1, "y": 1}, {"x": 2, "y": 2}),
        ({"x": math.nan, "y": 1}, {"x": 2, "y": 2}),
        ({"x": 1, "y": 1}, [2, 2]),
    ],
)
def test_virtual_line_geometry_is_strict(super_admin_user, start, end):
    _, camera = make_camera(super_admin_user, f"line-{uuid.uuid4().hex[:6]}")
    with pytest.raises(ValidationError):
        VirtualLine(
            camera=camera,
            line_start=start,
            line_end=end,
            created_by=super_admin_user,
        ).full_clean()


def test_virtual_line_human_configuration_and_machine_scope(
    api_client, super_admin_user
):
    _, camera_a = make_camera(super_admin_user, "line-a")
    _, camera_b = make_camera(super_admin_user, "line-b")
    credential, secret = make_machine(super_admin_user, [camera_a])
    api_client.force_authenticate(super_admin_user)
    created = api_client.post(
        reverse("api_v1:virtual-line-list"),
        {
            "camera": str(camera_a.pk),
            "line_start": {"x": 10, "y": 20},
            "line_end": {"x": 100, "y": 20},
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    VirtualLine.objects.create(
        camera=camera_b,
        line_start={"x": 1, "y": 1},
        line_end={"x": 2, "y": 2},
        created_by=super_admin_user,
    )
    api_client.force_authenticate(user=None)
    read = api_client.get(
        reverse("api_v1:virtual-line-list"),
        **machine_headers(credential, secret),
    )
    assert read.status_code == 200
    assert [row["id"] for row in results(read)] == [created.data["id"]]


def test_authorized_vehicle_current_lookup_and_history_are_independent(
    api_client, super_admin_user
):
    _, camera = make_camera(super_admin_user, "vehicle-history")
    credential, secret = make_machine(super_admin_user, [camera])
    CameraAIModel.objects.create(
        camera=camera,
        model_identifier=CameraAIModel.ModelIdentifier.ANPR,
        created_by=super_admin_user,
    )
    current = AuthorizedVehicle.objects.create(
        plate_number="ABC-123",
        responsible_name="Operations",
        created_by=super_admin_user,
    )
    expired = AuthorizedVehicle.objects.create(
        plate_number="OLD-123",
        responsible_name="Former contractor",
        expires_on=timezone.localdate() - timedelta(days=1),
        created_by=super_admin_user,
    )
    event = CameraEvent.objects.create(
        event_type=CameraEvent.EventType.VEHICLE_ENTRY,
        camera=camera,
        ingestion_credential=credential,
        source_event_id=uuid.uuid4(),
        plate_number=current.plate_number,
        direction=CameraEvent.Direction.ENTRY,
        authorized=True,
        detected_at=timezone.now(),
        created_by=credential.principal,
    )

    for plate, expected in ((" abc-123 ", True), (expired.plate_number, False), ("NOPE", False)):
        response = api_client.get(
            reverse("api_v1:authorized-vehicle-list"),
            {"plate_number": plate},
            **machine_headers(credential, secret),
        )
        assert response.status_code == 200
        assert response.data["authorized"] is expected
        assert "responsible_name" not in response.data

    current.is_active = False
    current.save(update_fields=["is_active", "updated_at"])
    event.refresh_from_db()
    assert event.authorized is True


def test_authorized_vehicle_human_crud_normalizes_and_soft_disables(
    api_client, super_admin_user
):
    api_client.force_authenticate(super_admin_user)
    created = api_client.post(
        reverse("api_v1:authorized-vehicle-list"),
        {"plate_number": " abc 123 ", "responsible_name": "Logistics"},
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.data["plate_number"] == "ABC 123"
    updated = api_client.patch(
        reverse("api_v1:authorized-vehicle-detail", kwargs={"pk": created.data["id"]}),
        {"responsible_name": "Facilities"},
        format="json",
    )
    deleted = api_client.delete(
        reverse("api_v1:authorized-vehicle-detail", kwargs={"pk": created.data["id"]})
    )
    assert updated.status_code == 200
    assert deleted.status_code == 204
    assert not AuthorizedVehicle.objects.filter(pk=created.data["id"]).exists()
    assert AuthorizedVehicle.all_objects.get(pk=created.data["id"]).is_active is False


def test_active_models_are_multiple_idempotent_independent_and_scoped(
    api_client, super_admin_user
):
    _, camera_a = make_camera(super_admin_user, "models-a")
    _, camera_b = make_camera(super_admin_user, "models-b")
    credential, secret = make_machine(super_admin_user, [camera_a])
    endpoint = reverse("api_v1:camera-active-models", kwargs={"camera_id": camera_a.pk})
    api_client.force_authenticate(super_admin_user)
    for identifier in ("fire_smoke", "intrusion"):
        response = api_client.post(endpoint, {"model_identifier": identifier}, format="json")
        assert response.status_code == 201, response.data
    duplicate = api_client.post(
        endpoint, {"model_identifier": "intrusion"}, format="json"
    )
    assert duplicate.status_code == 200
    assert CameraAIModel.objects.filter(camera=camera_a).count() == 2
    disabled = api_client.delete(
        reverse(
            "api_v1:camera-active-model-detail",
            kwargs={"camera_id": camera_a.pk, "model_identifier": "intrusion"},
        )
    )
    assert disabled.status_code == 204
    assert list(
        CameraAIModel.objects.filter(camera=camera_a).values_list(
            "model_identifier", flat=True
        )
    ) == ["fire_smoke"]

    api_client.force_authenticate(user=None)
    own = api_client.get(endpoint, **machine_headers(credential, secret))
    foreign = api_client.get(
        reverse("api_v1:camera-active-models", kwargs={"camera_id": camera_b.pk}),
        **machine_headers(credential, secret),
    )
    assert own.status_code == 200
    assert [row["model_identifier"] for row in own.data] == ["fire_smoke"]
    assert foreign.status_code == 403


def test_database_uniqueness_guards_configuration_identities(super_admin_user):
    _, camera = make_camera(super_admin_user, "constraints")
    make_roi(camera, super_admin_user, "unique")
    with pytest.raises(IntegrityError), transaction.atomic():
        CameraROI.objects.create(
            camera=camera,
            identifier="unique",
            name="Duplicate",
            polygon=TRIANGLE,
            created_by=super_admin_user,
        )
    CameraAIModel.objects.create(
        camera=camera,
        model_identifier="tamper",
        created_by=super_admin_user,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        CameraAIModel.objects.create(
            camera=camera,
            model_identifier="tamper",
            created_by=super_admin_user,
        )
    VirtualLine.objects.create(
        camera=camera,
        line_start={"x": 0, "y": 0},
        line_end={"x": 1, "y": 1},
        created_by=super_admin_user,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        VirtualLine.objects.create(
            camera=camera,
            line_start={"x": 2, "y": 2},
            line_end={"x": 3, "y": 3},
            created_by=super_admin_user,
        )


def test_only_super_admin_can_mutate_and_machine_is_read_only(
    api_client, super_admin_user, role_security_officer
):
    _, camera = make_camera(super_admin_user, "rbac")
    credential, secret = make_machine(super_admin_user, [camera])
    officer = User.objects.create_user(
        email="camera-config-officer@sflms.test",
        username="camera-config-officer",
        full_name="Camera Configuration Officer",
        password="StrongPass123!",
        role=role_security_officer,
    )
    payload = {
        "camera": str(camera.pk),
        "identifier": "rbac-zone",
        "name": "RBAC zone",
        "polygon": TRIANGLE,
    }
    api_client.force_authenticate(officer)
    denied_human = api_client.post(
        reverse("api_v1:camera-roi-list"), payload, format="json"
    )
    api_client.force_authenticate(user=None)
    denied_machine = api_client.post(
        reverse("api_v1:camera-roi-list"),
        payload,
        format="json",
        **machine_headers(credential, secret),
    )
    human_on_ingestion = api_client.post(
        reverse("api_v1:camera-event-list"), {}, format="json"
    )
    assert denied_human.status_code == 403
    assert denied_machine.status_code in {401, 403}
    assert human_on_ingestion.status_code in {401, 403}


@pytest.mark.parametrize("state", ["revoked", "expired", "camera", "facility"])
def test_unusable_machine_or_parent_state_denies_configuration(
    api_client, super_admin_user, state
):
    facility, camera = make_camera(super_admin_user, f"state-{state}")
    credential, secret = make_machine(super_admin_user, [camera])
    make_roi(camera, super_admin_user)
    if state == "revoked":
        credential.revoked_at = timezone.now()
        credential.revoked_by = super_admin_user
        credential.is_active = False
        credential.save(
            update_fields=["revoked_at", "revoked_by", "is_active", "updated_at"]
        )
    elif state == "expired":
        credential.expires_at = timezone.now() - timedelta(seconds=1)
        credential.save(update_fields=["expires_at", "updated_at"])
    elif state == "camera":
        camera.is_active = False
        camera.save(update_fields=["is_active", "updated_at"])
    else:
        facility.is_active = False
        facility.save(update_fields=["is_active", "updated_at"])
    response = api_client.get(
        reverse("api_v1:camera-roi-list"),
        **machine_headers(credential, secret),
    )
    if state in {"revoked", "expired"}:
        assert response.status_code in {401, 403}
    else:
        assert response.status_code == 200
        assert results(response) == []


def test_semantic_audits_emit_once_only_for_meaningful_mutations(
    api_client, super_admin_user
):
    _, camera = make_camera(super_admin_user, "audit")
    api_client.force_authenticate(super_admin_user)
    created = api_client.post(
        reverse("api_v1:camera-roi-list"),
        {
            "camera": str(camera.pk),
            "identifier": "audit-zone",
            "name": "Audit zone",
            "polygon": TRIANGLE,
        },
        format="json",
    )
    detail = reverse("api_v1:camera-roi-detail", kwargs={"pk": created.data["id"]})
    api_client.get(detail)
    api_client.patch(detail, {"name": "Audit zone"}, format="json")
    api_client.patch(detail, {"name": "Updated audit zone"}, format="json")
    api_client.delete(detail)
    api_client.delete(detail)
    assert AuditLog.objects.filter(action="camera_roi.created").count() == 1
    assert AuditLog.objects.filter(action="camera_roi.updated").count() == 1
    assert AuditLog.objects.filter(action="camera_roi.disabled").count() == 1
    assert not AuditLog.objects.filter(action__contains="read").exists()
    audit_payload = str(
        list(
            AuditLog.objects.filter(action__startswith="camera_roi").values(
                "before", "after"
            )
        )
    )
    assert "polygon" not in audit_payload
    assert "secret" not in audit_payload


@pytest.mark.django_db(transaction=True)
def test_concurrent_model_enable_is_idempotent_on_postgresql(super_admin_user):
    if connection.vendor == "sqlite":
        pytest.skip("True uniqueness races require the production PostgreSQL backend.")
    _, camera = make_camera(super_admin_user, "model-race")

    def enable():
        close_old_connections()
        thread_camera = Camera.objects.get(pk=camera.pk)
        thread_actor = User.objects.select_related("role").get(pk=super_admin_user.pk)
        try:
            return enable_camera_ai_model(
                camera=thread_camera,
                model_identifier=CameraAIModel.ModelIdentifier.ANPR,
                actor=thread_actor,
            )[1]
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        changed = list(pool.map(lambda _: enable(), range(2)))
    assert sorted(changed) == [False, True]
    assert CameraAIModel.objects.filter(camera=camera, model_identifier="anpr").count() == 1
    assert AuditLog.objects.filter(action="camera_ai_model.enabled").count() == 1
