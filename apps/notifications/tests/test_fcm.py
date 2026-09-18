import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from api.v1.camera_events.serializers import CameraEventCreateSerializer
from apps.facilities.models import FacilityAssignment
from apps.notifications.models import (
    DeviceRegistration,
    Notification,
    NotificationPreference,
    PushDelivery,
)
from apps.notifications.push import (
    enqueue_security_notifications,
    register_device,
    security_push_payload,
)
from apps.notifications.tasks import (
    TransientPushDeliveryError,
    deliver_push_notification,
    recover_queued_push_deliveries,
)
from apps.security.camera_events import create_camera_event, update_camera_event
from apps.security.models import AuthorizedVehicle, CameraEvent
from apps.security.tests.test_camera_events import (
    create_facility_camera,
    create_machine,
    payload_for,
)
from apps.users.models import User


pytestmark = pytest.mark.django_db


def create_event(actor, event_type, *, suffix, authorized=None):
    facility, camera = create_facility_camera(actor, suffix)
    credential, _ = create_machine(actor, camera, suffix)
    overrides = {}
    if authorized is not None:
        overrides["authorized"] = authorized
    payload = payload_for(camera, event_type, **overrides)
    if authorized is True:
        AuthorizedVehicle.objects.create(
            plate_number=payload["plate_number"],
            responsible_name="Authorized driver",
            created_by=actor,
        )
    serializer = CameraEventCreateSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    data = dict(serializer.validated_data)
    camera_id = data.pop("camera")
    source_event_id = data.pop("source_event_id")
    event, created = create_camera_event(
        credential=credential,
        source_event_id=source_event_id,
        camera_id=camera_id,
        data=data,
    )
    assert created is True
    return facility, camera, credential, source_event_id, data, event


def create_queued_delivery(actor, django_capture_on_commit_callbacks, suffix="delivery"):
    device = register_device(
        user=actor,
        token=f"fcm-registration-token-{suffix}",
        platform=DeviceRegistration.Platform.ANDROID,
    )
    with patch("apps.notifications.tasks.deliver_push_notification.delay"):
        with django_capture_on_commit_callbacks(execute=True):
            _, _, _, _, _, event = create_event(
                actor,
                CameraEvent.EventType.FIRE_ALERT,
                suffix=suffix,
            )
    notification = Notification.objects.get(
        source_id=event.security_alert_id,
        recipient=actor,
    )
    return event, device, PushDelivery.objects.get(
        notification=notification,
        device=device,
    )


def test_device_registration_api_is_private_idempotent_and_never_returns_token(
    api_client,
    super_admin_user,
):
    url = reverse("api_v1:notification-device-list")
    payload = {"token": "private-fcm-token-1", "platform": "android"}

    assert api_client.post(url, payload, format="json").status_code == 401
    api_client.force_authenticate(super_admin_user)
    created = api_client.post(url, payload, format="json")
    repeated = api_client.post(
        url,
        {"token": payload["token"], "platform": "ios"},
        format="json",
    )

    assert created.status_code == 201
    assert repeated.status_code == 201
    assert "token" not in created.data
    assert "token" not in repeated.data
    assert DeviceRegistration.objects.count() == 1
    assert DeviceRegistration.objects.get().platform == DeviceRegistration.Platform.IOS
    listing = api_client.get(url)
    assert listing.status_code == 200
    assert payload["token"] not in str(listing.data)


def test_device_update_unregister_and_cross_user_ownership(
    api_client,
    super_admin_user,
    role_security_officer,
):
    other = User.objects.create_user(
        email="device-other@sflms.test",
        username="device-other",
        full_name="Device Other",
        password="StrongPass123!",
        role=role_security_officer,
    )
    device = register_device(
        user=other,
        token="other-users-private-token",
        platform=DeviceRegistration.Platform.ANDROID,
    )
    api_client.force_authenticate(super_admin_user)

    conflict = api_client.post(
        reverse("api_v1:notification-device-list"),
        {"token": device.token, "platform": "ios"},
        format="json",
    )
    hidden = api_client.patch(
        reverse("api_v1:notification-device-detail", kwargs={"pk": device.pk}),
        {"platform": "ios"},
        format="json",
    )
    assert conflict.status_code == 400
    assert device.token not in str(conflict.data)
    assert hidden.status_code == 404

    own = register_device(
        user=super_admin_user,
        token="own-old-private-token",
        platform=DeviceRegistration.Platform.ANDROID,
    )
    detail_url = reverse("api_v1:notification-device-detail", kwargs={"pk": own.pk})
    updated = api_client.patch(
        detail_url,
        {"token": "own-new-private-token", "platform": "ios"},
        format="json",
    )
    removed = api_client.delete(detail_url)
    own.refresh_from_db()
    assert updated.status_code == 200
    assert "token" not in updated.data
    assert removed.status_code == 204
    assert own.is_active is False
    assert own.disabled_at is not None


def test_roleless_machine_principal_cannot_register_a_device(api_client):
    principal = User.objects.create_user(
        email="machine-device@sflms.test",
        username="machine-device",
        full_name="Machine Device",
        password=None,
        role=None,
    )
    api_client.force_authenticate(principal)
    response = api_client.post(
        reverse("api_v1:notification-device-list"),
        {"token": "machine-private-token", "platform": "android"},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "event_type",
    [
        CameraEvent.EventType.FIRE_ALERT,
        CameraEvent.EventType.SMOKE_ALERT,
        CameraEvent.EventType.INTRUSION_ALERT,
        CameraEvent.EventType.VEHICLE_ENTRY,
        CameraEvent.EventType.VEHICLE_EXIT,
        CameraEvent.EventType.TAMPER_ALERT,
    ],
)
def test_eligible_initial_camera_events_create_one_durable_notification(
    event_type,
    super_admin_user,
    django_capture_on_commit_callbacks,
):
    with patch("apps.notifications.tasks.deliver_push_notification.delay"):
        with django_capture_on_commit_callbacks(execute=True):
            _, _, credential, source_event_id, data, event = create_event(
                super_admin_user,
                event_type,
                suffix=f"eligible-{event_type}-{uuid.uuid4().hex[:6]}",
            )
        with django_capture_on_commit_callbacks(execute=True):
            repeated, created = create_camera_event(
                credential=credential,
                source_event_id=source_event_id,
                camera_id=event.camera_id,
                data=data,
            )
    assert created is False
    assert repeated.pk == event.pk
    assert Notification.objects.filter(
        recipient=super_admin_user,
        source_id=event.security_alert_id,
    ).count() == 1


def test_authorized_vehicle_does_not_create_alert_notification_or_push(
    super_admin_user,
    django_capture_on_commit_callbacks,
):
    with patch("apps.notifications.tasks.deliver_push_notification.delay") as delay:
        with django_capture_on_commit_callbacks(execute=True):
            _, _, _, _, _, event = create_event(
                super_admin_user,
                CameraEvent.EventType.VEHICLE_ENTRY,
                suffix="authorized-vehicle",
                authorized=True,
            )
    assert event.security_alert_id is None
    assert not Notification.objects.filter(source_id=event.pk).exists()
    delay.assert_not_called()


def test_alert_transaction_rollback_discards_notification_and_enqueue(
    super_admin_user,
    django_capture_on_commit_callbacks,
):
    facility, camera = create_facility_camera(super_admin_user, "push-rollback")
    credential, _ = create_machine(super_admin_user, camera, "push-rollback")
    payload = payload_for(camera, CameraEvent.EventType.FIRE_ALERT)
    serializer = CameraEventCreateSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    data = dict(serializer.validated_data)
    data.pop("camera")
    source_event_id = data.pop("source_event_id")
    with patch("apps.notifications.tasks.deliver_push_notification.delay") as delay:
        with patch(
            "apps.security.camera_events.record_audit",
            side_effect=RuntimeError("rollback test"),
        ):
            with django_capture_on_commit_callbacks(execute=True):
                with pytest.raises(RuntimeError, match="rollback test"):
                    create_camera_event(
                        credential=credential,
                        source_event_id=source_event_id,
                        camera_id=camera.pk,
                        data=data,
                    )
    assert not CameraEvent.objects.filter(camera=camera).exists()
    assert not Notification.objects.filter(
        source_type="security.securityalert",
        recipient=super_admin_user,
    ).exists()
    delay.assert_not_called()


def test_camera_event_patch_does_not_create_notification_or_push(
    super_admin_user,
    django_capture_on_commit_callbacks,
):
    event, _, delivery = create_queued_delivery(
        super_admin_user,
        django_capture_on_commit_callbacks,
        "patch-no-push",
    )
    before = Notification.objects.filter(source_id=event.security_alert_id).count()
    with patch("apps.notifications.tasks.deliver_push_notification.delay") as delay:
        with django_capture_on_commit_callbacks(execute=True):
            update_camera_event(
                event_id=event.pk,
                credential=event.ingestion_credential,
                changes={"confidence": event.confidence},
            )
    assert Notification.objects.filter(source_id=event.security_alert_id).count() == before
    assert PushDelivery.objects.filter(pk=delivery.pk).count() == 1
    delay.assert_not_called()


def test_recipient_resolution_honors_role_permission_assignment_and_preference(
    super_admin_user,
    role_security_officer,
    django_capture_on_commit_callbacks,
):
    facility, camera = create_facility_camera(super_admin_user, "recipient-scope")
    credential, _ = create_machine(super_admin_user, camera, "recipient-scope")
    assigned = User.objects.create_user(
        email="push-assigned@sflms.test",
        username="push-assigned",
        full_name="Push Assigned",
        password="StrongPass123!",
        role=role_security_officer,
    )
    unrelated = User.objects.create_user(
        email="push-unrelated@sflms.test",
        username="push-unrelated",
        full_name="Push Unrelated",
        password="StrongPass123!",
        role=role_security_officer,
    )
    opted_out = User.objects.create_user(
        email="push-opted-out@sflms.test",
        username="push-opted-out",
        full_name="Push Opted Out",
        password="StrongPass123!",
        role=role_security_officer,
    )
    for user in (assigned, opted_out):
        FacilityAssignment.objects.create(
            facility=facility,
            user=user,
            role_type=FacilityAssignment.RoleType.SECURITY_OFFICER,
            created_by=super_admin_user,
        )
    NotificationPreference.objects.create(
        user=opted_out,
        critical_alerts=False,
        created_by=opted_out,
    )
    payload = payload_for(camera, CameraEvent.EventType.INTRUSION_ALERT)
    serializer = CameraEventCreateSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    data = dict(serializer.validated_data)
    data.pop("camera")
    source_event_id = data.pop("source_event_id")
    with patch("apps.notifications.tasks.deliver_push_notification.delay"):
        with django_capture_on_commit_callbacks(execute=True):
            event, _ = create_camera_event(
                credential=credential,
                source_event_id=source_event_id,
                camera_id=camera.pk,
                data=data,
            )
    recipients = set(
        Notification.objects.filter(source_id=event.security_alert_id).values_list(
            "recipient_id", flat=True
        )
    )
    assert recipients == {super_admin_user.pk, assigned.pk}
    assert unrelated.pk not in recipients
    assert opted_out.pk not in recipients


def test_success_records_sanitized_payload_and_does_not_resend(
    super_admin_user,
    django_capture_on_commit_callbacks,
):
    event, _, delivery = create_queued_delivery(
        super_admin_user,
        django_capture_on_commit_callbacks,
        "success",
    )
    with patch("apps.notifications.tasks.send_push", return_value="projects/test/messages/1") as send:
        assert deliver_push_notification.run(str(delivery.pk)) == PushDelivery.Status.SENT
        assert deliver_push_notification.run(str(delivery.pk)) == PushDelivery.Status.SENT
    delivery.refresh_from_db()
    assert delivery.status == PushDelivery.Status.SENT
    assert delivery.attempt_count == 1
    assert send.call_count == 1
    payload = send.call_args.kwargs["data"]
    assert payload == security_push_payload(event.security_alert, event)
    assert set(payload) == {
        "type",
        "alert_id",
        "event_type",
        "severity",
        "facility_id",
        "camera_id",
    }
    assert "snapshot" not in str(payload).lower()


def test_invalid_token_disables_only_that_device(
    super_admin_user,
    django_capture_on_commit_callbacks,
):
    from firebase_admin import messaging

    _, device, delivery = create_queued_delivery(
        super_admin_user,
        django_capture_on_commit_callbacks,
        "invalid",
    )
    with patch(
        "apps.notifications.tasks.send_push",
        side_effect=messaging.UnregisteredError("unregistered"),
    ):
        result = deliver_push_notification.run(str(delivery.pk))
    device.refresh_from_db()
    delivery.refresh_from_db()
    assert result == PushDelivery.Status.INVALID_TOKEN
    assert device.is_active is False
    assert delivery.status == PushDelivery.Status.INVALID_TOKEN
    assert delivery.notification.is_active is True


def test_partial_device_failure_does_not_resend_or_fail_successful_devices(
    super_admin_user,
    django_capture_on_commit_callbacks,
):
    from firebase_admin import messaging

    _, first_device, first_delivery = create_queued_delivery(
        super_admin_user,
        django_capture_on_commit_callbacks,
        "partial-first",
    )
    second_device = register_device(
        user=super_admin_user,
        token="fcm-registration-token-partial-second",
        platform="ios",
    )
    second_delivery = PushDelivery.objects.create(
        notification=first_delivery.notification,
        device=second_device,
    )
    with patch(
        "apps.notifications.tasks.send_push",
        side_effect=[messaging.UnregisteredError("unregistered"), "messages/second"],
    ) as send:
        deliver_push_notification.run(str(first_delivery.pk))
        deliver_push_notification.run(str(second_delivery.pk))
        deliver_push_notification.run(str(second_delivery.pk))
    first_device.refresh_from_db()
    first_delivery.refresh_from_db()
    second_delivery.refresh_from_db()
    assert first_device.is_active is False
    assert first_delivery.status == PushDelivery.Status.INVALID_TOKEN
    assert second_delivery.status == PushDelivery.Status.SENT
    assert send.call_count == 2


def test_enqueue_is_idempotent_per_notification_and_device(
    super_admin_user,
    django_capture_on_commit_callbacks,
):
    _, _, delivery = create_queued_delivery(
        super_admin_user,
        django_capture_on_commit_callbacks,
        "enqueue-idempotent",
    )
    with patch("apps.notifications.tasks.deliver_push_notification.delay") as delay:
        enqueue_security_notifications([delivery.notification_id])
        enqueue_security_notifications([delivery.notification_id])
    assert PushDelivery.objects.filter(notification=delivery.notification).count() == 1
    assert delay.call_count == 2


def test_missing_fcm_credentials_is_recorded_as_failed_not_sent(
    super_admin_user,
    django_capture_on_commit_callbacks,
    settings,
):
    settings.FCM_ENABLED = False
    settings.FCM_PROJECT_ID = ""
    settings.FCM_CREDENTIALS_PATH = ""
    _, _, delivery = create_queued_delivery(
        super_admin_user,
        django_capture_on_commit_callbacks,
        "unconfigured",
    )
    assert deliver_push_notification.run(str(delivery.pk)) == PushDelivery.Status.FAILED
    delivery.refresh_from_db()
    assert delivery.status == PushDelivery.Status.FAILED
    assert delivery.failure_code == "fcm_unavailable"


def test_assignment_removed_before_dispatch_is_skipped(
    super_admin_user,
    role_security_officer,
    django_capture_on_commit_callbacks,
):
    facility, camera = create_facility_camera(super_admin_user, "removed-assignment")
    credential, _ = create_machine(super_admin_user, camera, "removed-assignment")
    officer = User.objects.create_user(
        email="removed-assignment@sflms.test",
        username="removed-assignment",
        full_name="Removed Assignment",
        password="StrongPass123!",
        role=role_security_officer,
    )
    assignment = FacilityAssignment.objects.create(
        facility=facility,
        user=officer,
        role_type=FacilityAssignment.RoleType.SECURITY_OFFICER,
        created_by=super_admin_user,
    )
    device = register_device(
        user=officer,
        token="removed-assignment-token",
        platform="android",
    )
    payload = payload_for(camera, CameraEvent.EventType.FIRE_ALERT)
    serializer = CameraEventCreateSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    data = dict(serializer.validated_data)
    data.pop("camera")
    source_event_id = data.pop("source_event_id")
    with patch("apps.notifications.tasks.deliver_push_notification.delay"):
        with django_capture_on_commit_callbacks(execute=True):
            event, _ = create_camera_event(
                credential=credential,
                source_event_id=source_event_id,
                camera_id=camera.pk,
                data=data,
            )
    delivery = PushDelivery.objects.get(
        notification__source_id=event.security_alert_id,
        device=device,
    )
    assignment.soft_delete()
    with patch("apps.notifications.tasks.send_push") as send:
        result = deliver_push_notification.run(str(delivery.pk))
    delivery.refresh_from_db()
    assert result == PushDelivery.Status.SKIPPED
    assert delivery.status == PushDelivery.Status.SKIPPED
    assert delivery.notification.is_active is True
    send.assert_not_called()


def test_transient_failure_is_queued_for_bounded_retry(
    super_admin_user,
    django_capture_on_commit_callbacks,
):
    from firebase_admin import exceptions as firebase_exceptions

    _, _, delivery = create_queued_delivery(
        super_admin_user,
        django_capture_on_commit_callbacks,
        "transient",
    )
    with patch(
        "apps.notifications.tasks.send_push",
        side_effect=firebase_exceptions.UnavailableError("temporary"),
    ):
        with pytest.raises(TransientPushDeliveryError):
            deliver_push_notification.run(str(delivery.pk))
    delivery.refresh_from_db()
    assert delivery.status == PushDelivery.Status.QUEUED
    assert delivery.failure_code == "transient_provider_error"
    assert delivery.attempt_count == 1
    assert deliver_push_notification.max_retries == 5


def test_recovery_requeues_stale_claims_without_resending_sent_deliveries(
    super_admin_user,
    django_capture_on_commit_callbacks,
):
    _, _, delivery = create_queued_delivery(
        super_admin_user,
        django_capture_on_commit_callbacks,
        "recovery",
    )
    delivery.status = PushDelivery.Status.PROCESSING
    delivery.processing_started_at = timezone.now() - timedelta(minutes=11)
    delivery.save(update_fields=["status", "processing_started_at", "updated_at"])
    with patch("apps.notifications.tasks.deliver_push_notification.delay") as delay:
        count = recover_queued_push_deliveries.run()
    delivery.refresh_from_db()
    assert count == 1
    assert delivery.status == PushDelivery.Status.QUEUED
    delay.assert_called_once_with(str(delivery.pk))
