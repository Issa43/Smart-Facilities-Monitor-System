import json
from datetime import timedelta

import pytest
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory

from apps.audit.models import AuditLog
from apps.facilities.models import Facility
from apps.security.authentication import AIIngestionAuthentication
from apps.security.machine_credentials import (
    camera_for_ingestion,
    can_ingest_camera_event,
    create_ai_ingestion_credential,
    verify_machine_secret,
)
from apps.security.models import (
    AIIngestionCameraScope,
    AIIngestionCredential,
    Camera,
)
from apps.users.models import User


pytestmark = pytest.mark.django_db


def create_facility_and_camera(actor, suffix):
    facility = Facility.objects.create(
        name=f"AI Facility {suffix}",
        type=Facility.Type.INDUSTRIAL,
        location="Riyadh",
        created_by=actor,
    )
    camera = Camera.objects.create(
        facility=facility,
        code=f"AI-CAM-{suffix}",
        name=f"AI Camera {suffix}",
        zone="Gate",
        created_by=actor,
    )
    return facility, camera


def create_human(role, suffix):
    return User.objects.create_user(
        email=f"{suffix}@sflms.test",
        username=suffix,
        full_name=suffix.replace("-", " ").title(),
        password="StrongPass123!",
        role=role,
    )


def create_credential(actor, camera, name="Gate integration"):
    return create_ai_ingestion_credential(
        name=name,
        actor=actor,
        cameras=[camera],
        expires_at=timezone.now() + timedelta(days=30),
    )


def authenticate(key_id, secret):
    request = APIRequestFactory().get(
        "/future-machine-endpoint/",
        HTTP_AUTHORIZATION=f"AIKey {key_id}:{secret}",
    )
    return AIIngestionAuthentication().authenticate(request)


def test_super_admin_create_returns_secret_once_and_stores_only_hash(
    api_client, super_admin_user
):
    _, camera = create_facility_and_camera(super_admin_user, "create")
    api_client.force_authenticate(super_admin_user)
    response = api_client.post(
        reverse("api_v1:ai-ingestion-credential-list"),
        {
            "name": "Gate service",
            "camera_ids": [str(camera.pk)],
            "expires_at": (timezone.now() + timedelta(days=30)).isoformat(),
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    secret = response.data["secret"]
    credential = AIIngestionCredential.objects.get(pk=response.data["id"])
    assert secret
    assert credential.secret_hash != secret
    assert check_password(secret, credential.secret_hash)
    assert credential.principal.role is None
    assert not credential.principal.has_usable_password()
    assert response.data["authorization_scheme"] == "AIKey"
    assert response.data["camera_scopes"][0]["facility_id"] == str(
        camera.facility_id
    )

    listing = api_client.get(reverse("api_v1:ai-ingestion-credential-list"))
    detail = api_client.get(
        reverse(
            "api_v1:ai-ingestion-credential-detail",
            kwargs={"pk": credential.pk},
        )
    )
    for safe_response in (listing, detail):
        serialized = json.dumps(safe_response.data)
        assert safe_response.status_code == 200
        assert "secret_hash" not in serialized
        assert secret not in serialized


def test_rotation_invalidates_old_secret_and_returns_new_secret_once(
    api_client, super_admin_user
):
    _, camera = create_facility_and_camera(super_admin_user, "rotate")
    credential, old_secret = create_credential(super_admin_user, camera)
    assert authenticate(credential.key_id, old_secret)[0] == credential.principal

    api_client.force_authenticate(super_admin_user)
    response = api_client.post(
        reverse(
            "api_v1:ai-ingestion-credential-rotate",
            kwargs={"pk": credential.pk},
        )
    )
    assert response.status_code == 200
    new_secret = response.data["secret"]
    assert new_secret != old_secret
    with pytest.raises(AuthenticationFailed):
        authenticate(credential.key_id, old_secret)
    assert authenticate(credential.key_id, new_secret)[0] == credential.principal

    detail = api_client.get(
        reverse(
            "api_v1:ai-ingestion-credential-detail",
            kwargs={"pk": credential.pk},
        )
    )
    assert "secret" not in detail.data
    assert AuditLog.objects.filter(
        action="ai_ingestion_credential.rotated",
        actor=super_admin_user,
        entity_id=str(credential.pk),
    ).count() == 1


def test_revoked_and_expired_credentials_cannot_authenticate(super_admin_user):
    _, camera = create_facility_and_camera(super_admin_user, "states")
    revoked, revoked_secret = create_credential(super_admin_user, camera, "Revoked")
    revoked.is_active = False
    revoked.revoked_at = timezone.now()
    revoked.revoked_by = super_admin_user
    revoked.save(update_fields=["is_active", "revoked_at", "revoked_by"])
    with pytest.raises(AuthenticationFailed):
        authenticate(revoked.key_id, revoked_secret)

    expired, expired_secret = create_credential(super_admin_user, camera, "Expired")
    expired.expires_at = timezone.now() - timedelta(seconds=1)
    expired.save(update_fields=["expires_at"])
    with pytest.raises(AuthenticationFailed):
        authenticate(expired.key_id, expired_secret)


@pytest.mark.parametrize(
    "header",
    [
        "AIKey",
        "AIKey missing-separator",
        "AIKey :",
        "AIKey key:",
        "AIKey :secret",
        "AIKey one:two extra",
    ],
)
def test_malformed_machine_credentials_fail_safely(header):
    request = APIRequestFactory().get(
        "/future-machine-endpoint/",
        HTTP_AUTHORIZATION=header,
    )
    with pytest.raises(AuthenticationFailed) as exc:
        AIIngestionAuthentication().authenticate(request)
    assert str(exc.value.detail) == "Invalid machine credentials."


def test_unknown_key_and_wrong_secret_have_generic_errors(super_admin_user):
    _, camera = create_facility_and_camera(super_admin_user, "invalid")
    credential, _ = create_credential(super_admin_user, camera)
    for key_id, secret in (("aic_unknown", "wrong"), (credential.key_id, "wrong")):
        with pytest.raises(AuthenticationFailed) as exc:
            authenticate(key_id, secret)
        assert str(exc.value.detail) == "Invalid machine credentials."


def test_machine_principal_cannot_obtain_human_jwt_or_receive_human_role(
    api_client, super_admin_user, role_security_officer
):
    _, camera = create_facility_and_camera(super_admin_user, "roleless")
    credential, _ = create_credential(super_admin_user, camera)
    principal = credential.principal

    login = api_client.post(
        reverse("auth-login"),
        {"email": principal.email, "password": "any-password"},
        format="json",
    )
    assert login.status_code == 401
    assert "access" not in login.data
    assert "refresh" not in login.data

    api_client.force_authenticate(super_admin_user)
    role_change = api_client.patch(
        reverse("user-detail", kwargs={"pk": principal.pk}),
        {"role": str(role_security_officer.pk)},
        format="json",
    )
    assert role_change.status_code == 400
    principal.refresh_from_db()
    assert principal.role is None


def test_camera_scope_and_facility_are_derived_from_authorized_camera(
    super_admin_user,
):
    facility, scoped = create_facility_and_camera(super_admin_user, "scoped")
    other_facility, unscoped = create_facility_and_camera(
        super_admin_user, "unscoped"
    )
    credential, _ = create_credential(super_admin_user, scoped)

    assert can_ingest_camera_event(credential, scoped)
    assert not can_ingest_camera_event(credential, unscoped)
    resolved = camera_for_ingestion(credential, scoped.pk)
    assert resolved.facility_id == facility.pk
    assert resolved.facility_id != other_facility.pk
    with pytest.raises(ValidationError) as exc:
        camera_for_ingestion(credential, unscoped.pk)
    assert "Camera is not available for ingestion" in str(exc.value)


def test_inactive_scope_revoked_and_expired_credentials_fail_camera_scope(
    super_admin_user,
):
    _, camera = create_facility_and_camera(super_admin_user, "scope-state")
    credential, _ = create_credential(super_admin_user, camera)
    scope = AIIngestionCameraScope.objects.get(
        credential=credential,
        camera=camera,
    )
    scope.is_active = False
    scope.save(update_fields=["is_active"])
    assert not can_ingest_camera_event(credential, camera)

    scope.is_active = True
    scope.save(update_fields=["is_active"])
    credential.expires_at = timezone.now() - timedelta(seconds=1)
    credential.save(update_fields=["expires_at"])
    assert not can_ingest_camera_event(credential, camera)

    credential.expires_at = None
    credential.is_active = False
    credential.revoked_at = timezone.now()
    credential.revoked_by = super_admin_user
    credential.save(
        update_fields=["expires_at", "is_active", "revoked_at", "revoked_by"]
    )
    assert not can_ingest_camera_event(credential, camera)


def test_only_super_admin_can_manage_machine_credentials(
    api_client,
    super_admin_user,
    role_security_officer,
    role_operations_manager,
    role_construction_manager,
):
    _, camera = create_facility_and_camera(super_admin_user, "rbac")
    url = reverse("api_v1:ai-ingestion-credential-list")
    humans = [
        create_human(role_security_officer, "machine-rbac-security"),
        create_human(role_operations_manager, "machine-rbac-operations"),
        create_human(role_construction_manager, "machine-rbac-construction"),
    ]
    machine_credential, _ = create_credential(super_admin_user, camera)
    humans.append(machine_credential.principal)

    for user in humans:
        api_client.force_authenticate(user)
        assert api_client.get(url).status_code == 403
        assert api_client.post(url, {"name": "Denied"}, format="json").status_code == 403

    api_client.force_authenticate(super_admin_user)
    assert api_client.get(url).status_code == 200


def test_scope_add_remove_and_revoke_create_safe_semantic_audits(
    api_client, super_admin_user
):
    _, first = create_facility_and_camera(super_admin_user, "audit-one")
    _, second = create_facility_and_camera(super_admin_user, "audit-two")
    api_client.force_authenticate(super_admin_user)
    created = api_client.post(
        reverse("api_v1:ai-ingestion-credential-list"),
        {"name": "Audited integration", "camera_ids": [str(first.pk)]},
        format="json",
    )
    secret = created.data["secret"]
    credential_id = created.data["id"]

    added = api_client.post(
        reverse(
            "api_v1:ai-ingestion-credential-add-scope",
            kwargs={"pk": credential_id},
        ),
        {"camera_id": str(second.pk)},
        format="json",
    )
    assert added.status_code == 201
    removed = api_client.delete(
        reverse(
            "api_v1:ai-ingestion-credential-remove-scope",
            kwargs={"pk": credential_id, "camera_id": second.pk},
        )
    )
    assert removed.status_code == 200
    revoked = api_client.post(
        reverse(
            "api_v1:ai-ingestion-credential-revoke",
            kwargs={"pk": credential_id},
        )
    )
    assert revoked.status_code == 200
    with pytest.raises(AuthenticationFailed):
        authenticate(created.data["key_id"], secret)

    actions = set(
        AuditLog.objects.filter(entity_id__in=[credential_id]).values_list(
            "action", flat=True
        )
    )
    scope_actions = set(
        AuditLog.objects.filter(
            action__in=[
                "ai_ingestion_credential.scope_added",
                "ai_ingestion_credential.scope_removed",
            ]
        ).values_list("action", flat=True)
    )
    assert "ai_ingestion_credential.created" in actions
    assert "ai_ingestion_credential.revoked" in actions
    assert scope_actions == {
        "ai_ingestion_credential.scope_added",
        "ai_ingestion_credential.scope_removed",
    }
    audit_payload = json.dumps(
        list(AuditLog.objects.values("before", "after", "entity_ref")),
        default=str,
    )
    credential = AIIngestionCredential.all_objects.get(pk=credential_id)
    assert secret not in audit_payload
    assert credential.secret_hash not in audit_payload


def test_machine_authentication_does_not_create_audit_spam(super_admin_user):
    _, camera = create_facility_and_camera(super_admin_user, "no-auth-audit")
    credential, secret = create_credential(super_admin_user, camera)
    before = AuditLog.objects.count()
    principal, authenticated_credential = authenticate(credential.key_id, secret)
    assert principal == credential.principal
    assert authenticated_credential == credential
    assert AuditLog.objects.count() == before


def test_duplicate_key_id_and_camera_scope_are_database_constrained(
    super_admin_user,
):
    _, camera = create_facility_and_camera(super_admin_user, "unique")
    credential, secret = create_credential(super_admin_user, camera)
    assert verify_machine_secret(secret, credential.secret_hash)

    second_principal = User.objects.create_user(
        email="second-machine@machine.sflms.invalid",
        username="second-machine",
        full_name="Second machine",
        password=None,
        role=None,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        AIIngestionCredential.objects.create(
            name="Duplicate key",
            principal=second_principal,
            key_id=credential.key_id,
            secret_hash=credential.secret_hash,
            created_by=super_admin_user,
        )

    with pytest.raises(IntegrityError), transaction.atomic():
        AIIngestionCameraScope.objects.create(
            credential=credential,
            camera=camera,
            created_by=super_admin_user,
        )
