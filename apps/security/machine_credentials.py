import secrets
import uuid

from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record_audit
from apps.users.models import Role, User

from .models import AIIngestionCameraScope, AIIngestionCredential, Camera


MACHINE_SECRET_BYTES = 32
_DUMMY_SECRET_HASH = make_password("invalid-machine-credential")


def generate_machine_secret():
    return secrets.token_urlsafe(MACHINE_SECRET_BYTES)


def hash_machine_secret(secret):
    """Use Django's configured password hasher; plaintext is never persisted."""
    return make_password(secret)


def verify_machine_secret(secret, encoded_secret):
    """Django password hashers perform constant-time digest comparison."""
    return check_password(secret, encoded_secret)


def perform_dummy_secret_check(secret):
    """Reduce key-id enumeration signal when a public key id is unknown."""
    check_password(secret, _DUMMY_SECRET_HASH)


def _require_super_admin(actor):
    if not (
        actor
        and getattr(actor, "is_authenticated", False)
        and actor.is_active
        and actor.role_id
        and actor.role.name == Role.SUPER_ADMIN
    ):
        raise ValidationError({"actor": "An active Super Admin is required."})


def _safe_credential_state(credential):
    return {
        "key_id": credential.key_id,
        "principal_id": str(credential.principal_id),
        "is_active": credential.is_active,
        "expires_at": (
            credential.expires_at.isoformat() if credential.expires_at else None
        ),
        "revoked_at": (
            credential.revoked_at.isoformat() if credential.revoked_at else None
        ),
    }


def _resolve_cameras(cameras):
    camera_ids = {camera.pk if isinstance(camera, Camera) else camera for camera in cameras}
    resolved = list(
        Camera.objects.filter(pk__in=camera_ids).select_related("facility")
    )
    if len(resolved) != len(camera_ids):
        raise ValidationError({"camera_ids": "Every camera scope must be active."})
    for camera in resolved:
        if not camera.facility.is_active:
            raise ValidationError(
                {"camera_ids": "Camera scopes require an active facility."}
            )
    return resolved


@transaction.atomic
def create_ai_ingestion_credential(
    *, name, actor, cameras=(), expires_at=None, request=None
):
    _require_super_admin(actor)
    if not (name or "").strip():
        raise ValidationError({"name": "A credential name is required."})
    if expires_at and expires_at <= timezone.now():
        raise ValidationError({"expires_at": "Expiration must be in the future."})
    resolved_cameras = _resolve_cameras(cameras)

    principal_uuid = uuid.uuid4()
    principal = User.objects.create_user(
        email=f"ai-{principal_uuid.hex}@machine.sflms.invalid",
        username=f"ai-{principal_uuid.hex}",
        full_name=f"AI service: {name.strip()}"[:150],
        password=None,
        role=None,
        status=User.STATUS_ACTIVE,
    )
    secret = generate_machine_secret()
    credential = AIIngestionCredential(
        name=name.strip(),
        principal=principal,
        secret_hash=hash_machine_secret(secret),
        expires_at=expires_at,
        created_by=actor,
    )
    credential.full_clean()
    credential.save()

    for camera in resolved_cameras:
        add_ai_ingestion_camera_scope(
            credential=credential,
            camera=camera,
            actor=actor,
            request=request,
        )

    record_audit(
        actor=actor,
        action="ai_ingestion_credential.created",
        entity=credential,
        after=_safe_credential_state(credential),
        request=request,
    )
    return credential, secret


@transaction.atomic
def rotate_ai_ingestion_credential(*, credential_id, actor, request=None):
    _require_super_admin(actor)
    credential = (
        AIIngestionCredential.all_objects.select_for_update()
        .select_related("principal")
        .get(pk=credential_id)
    )
    if not credential.is_usable:
        raise ValidationError(
            {"credential": "Only an active, unexpired credential can be rotated."}
        )
    secret = generate_machine_secret()
    credential.secret_hash = hash_machine_secret(secret)
    credential.full_clean()
    credential.save(update_fields=["secret_hash", "updated_at"])
    record_audit(
        actor=actor,
        action="ai_ingestion_credential.rotated",
        entity=credential,
        after={"key_id": credential.key_id, "rotated": True},
        request=request,
    )
    return credential, secret


@transaction.atomic
def revoke_ai_ingestion_credential(*, credential_id, actor, request=None):
    _require_super_admin(actor)
    credential = (
        AIIngestionCredential.all_objects.select_for_update()
        .select_related("principal")
        .get(pk=credential_id)
    )
    if credential.revoked_at:
        return credential
    before = _safe_credential_state(credential)
    credential.is_active = False
    credential.revoked_at = timezone.now()
    credential.revoked_by = actor
    credential.full_clean()
    credential.save(
        update_fields=["is_active", "revoked_at", "revoked_by", "updated_at"]
    )
    record_audit(
        actor=actor,
        action="ai_ingestion_credential.revoked",
        entity=credential,
        before=before,
        after=_safe_credential_state(credential),
        request=request,
    )
    return credential


@transaction.atomic
def add_ai_ingestion_camera_scope(*, credential, camera, actor, request=None):
    _require_super_admin(actor)
    credential = (
        AIIngestionCredential.all_objects.select_for_update()
        .select_related("principal")
        .get(pk=credential.pk)
    )
    if not credential.is_active or credential.revoked_at:
        raise ValidationError(
            {"credential": "A revoked or inactive credential cannot receive scopes."}
        )
    camera = Camera.objects.select_related("facility").get(pk=camera.pk)
    if not camera.facility.is_active:
        raise ValidationError({"camera": "The camera facility must be active."})

    scope = AIIngestionCameraScope.all_objects.filter(
        credential=credential,
        camera=camera,
    ).first()
    changed = scope is None or not scope.is_active
    if scope is None:
        scope = AIIngestionCameraScope(
            credential=credential,
            camera=camera,
            created_by=actor,
        )
    elif not scope.is_active:
        scope.is_active = True
    scope.full_clean()
    scope.save()
    if changed:
        record_audit(
            actor=actor,
            action="ai_ingestion_credential.scope_added",
            entity=scope,
            after={
                "credential_id": str(credential.pk),
                "key_id": credential.key_id,
                "camera_id": str(camera.pk),
                "facility_id": str(camera.facility_id),
            },
            request=request,
        )
    return scope


@transaction.atomic
def remove_ai_ingestion_camera_scope(*, credential, camera, actor, request=None):
    _require_super_admin(actor)
    scope = (
        AIIngestionCameraScope.all_objects.select_for_update()
        .select_related("credential", "camera__facility")
        .get(credential=credential, camera=camera)
    )
    if scope.is_active:
        scope.is_active = False
        scope.save(update_fields=["is_active", "updated_at"])
        record_audit(
            actor=actor,
            action="ai_ingestion_credential.scope_removed",
            entity=scope,
            before={
                "credential_id": str(scope.credential_id),
                "key_id": scope.credential.key_id,
                "camera_id": str(scope.camera_id),
                "facility_id": str(scope.camera.facility_id),
                "is_active": True,
            },
            after={"is_active": False},
            request=request,
        )
    return scope


def can_ingest_camera_event(credential, camera):
    """Return whether this machine credential currently owns this camera scope."""
    if not credential or not camera:
        return False
    try:
        if not credential.is_usable:
            return False
    except (AIIngestionCredential.DoesNotExist, User.DoesNotExist):
        return False
    return AIIngestionCameraScope.objects.filter(
        credential=credential,
        camera=camera,
        camera__is_active=True,
        camera__facility__is_active=True,
    ).exists()


def camera_for_ingestion(credential, camera_id):
    """Resolve an authorized Camera; callers derive facility from the result."""
    camera = Camera.objects.select_related("facility").filter(pk=camera_id).first()
    if not camera or not can_ingest_camera_event(credential, camera):
        raise ValidationError({"camera_id": "Camera is not available for ingestion."})
    return camera
