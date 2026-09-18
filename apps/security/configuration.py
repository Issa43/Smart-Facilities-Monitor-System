from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import record_audit
from apps.users.models import Role

from .models import AuthorizedVehicle, CameraAIModel


def require_super_admin(actor):
    if not (
        actor
        and getattr(actor, "is_authenticated", False)
        and actor.is_active
        and actor.role_id
        and actor.role.name == Role.SUPER_ADMIN
    ):
        raise ValidationError({"actor": "An active Super Admin is required."})


def _safe_configuration_state(instance):
    state = {
        "id": str(instance.pk),
        "is_active": instance.is_active,
    }
    if hasattr(instance, "camera_id"):
        state["camera_id"] = str(instance.camera_id)
    if hasattr(instance, "roi_id"):
        state["roi_id"] = str(instance.roi_id)
        state["camera_id"] = str(instance.roi.camera_id)
    for field in (
        "identifier",
        "name",
        "plate_number",
        "responsible_name",
        "expires_on",
        "model_identifier",
        "always_restricted",
        "timezone_name",
    ):
        if hasattr(instance, field):
            value = getattr(instance, field)
            state[field] = value.isoformat() if hasattr(value, "isoformat") else value
    return state


@transaction.atomic
def create_configuration(*, model, values, actor, action):
    require_super_admin(actor)
    instance = model(**values, created_by=actor)
    instance.full_clean()
    instance.save()
    record_audit(
        actor=actor,
        action=action,
        entity=instance,
        after=_safe_configuration_state(instance),
    )
    return instance


@transaction.atomic
def update_configuration(*, instance, values, actor, action):
    require_super_admin(actor)
    instance = (
        instance.__class__.all_objects.select_for_update(of=("self",))
        .select_related(*_select_related_for(instance))
        .get(pk=instance.pk)
    )
    before = _safe_configuration_state(instance)
    changed = False
    for field, value in values.items():
        if getattr(instance, field) != value:
            setattr(instance, field, value)
            changed = True
    if not changed:
        return instance
    instance.full_clean()
    instance.save(update_fields=[*values.keys(), "updated_at"])
    record_audit(
        actor=actor,
        action=action,
        entity=instance,
        before=before,
        after=_safe_configuration_state(instance),
    )
    return instance


def _select_related_for(instance):
    if hasattr(instance, "roi_id"):
        return ("roi__camera__facility",)
    if hasattr(instance, "camera_id"):
        return ("camera__facility",)
    return ()


@transaction.atomic
def disable_configuration(*, instance, actor, action):
    require_super_admin(actor)
    instance = instance.__class__.all_objects.select_for_update(of=("self",)).get(
        pk=instance.pk
    )
    if not instance.is_active:
        return instance, False
    before = _safe_configuration_state(instance)
    instance.is_active = False
    instance.save(update_fields=["is_active", "updated_at"])
    record_audit(
        actor=actor,
        action=action,
        entity=instance,
        before=before,
        after=_safe_configuration_state(instance),
    )
    return instance, True


def enable_camera_ai_model(*, camera, model_identifier, actor):
    require_super_admin(actor)
    try:
        with transaction.atomic():
            assignment = (
                CameraAIModel.all_objects.select_for_update(of=("self",))
                .filter(camera=camera, model_identifier=model_identifier)
                .first()
            )
            changed = assignment is None or not assignment.is_active
            if assignment is None:
                assignment = CameraAIModel(
                    camera=camera,
                    model_identifier=model_identifier,
                    created_by=actor,
                )
            elif not assignment.is_active:
                assignment.is_active = True
            assignment.full_clean(validate_unique=False, validate_constraints=False)
            assignment.save()
            if changed:
                record_audit(
                    actor=actor,
                    action="camera_ai_model.enabled",
                    entity=assignment,
                    after=_safe_configuration_state(assignment),
                )
            return assignment, changed
    except IntegrityError:
        # A concurrent request may win the unique (camera, model) insert race.
        # Returning that active row makes repeated enable requests idempotent.
        assignment = CameraAIModel.objects.filter(
            camera=camera,
            model_identifier=model_identifier,
        ).first()
        if assignment is None:
            raise
        return assignment, False


@transaction.atomic
def disable_camera_ai_model(*, assignment, actor):
    return disable_configuration(
        instance=assignment,
        actor=actor,
        action="camera_ai_model.disabled",
    )


def currently_authorized_vehicle(plate_number):
    normalized = AuthorizedVehicle.normalize_plate(plate_number)
    if not normalized:
        return None
    return (
        AuthorizedVehicle.objects.filter(plate_number=normalized)
        .filter(Q(expires_on__isnull=True) | Q(expires_on__gte=timezone.localdate()))
        .first()
    )
