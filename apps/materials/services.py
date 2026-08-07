from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Material, MaterialConsumptionRecord, MaterialRequest


REQUEST_TRANSITIONS = {
    MaterialRequest.Status.SUBMITTED: {
        MaterialRequest.Status.REVIEWED,
        MaterialRequest.Status.REJECTED,
    },
    MaterialRequest.Status.REVIEWED: {
        MaterialRequest.Status.APPROVED,
        MaterialRequest.Status.REJECTED,
    },
    MaterialRequest.Status.APPROVED: {MaterialRequest.Status.COMPLETED},
    MaterialRequest.Status.REJECTED: set(),
    MaterialRequest.Status.COMPLETED: set(),
}


def _as_material_quantity(value):
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({"quantity": "A valid decimal quantity is required."}) from exc

    if not quantity.is_finite():
        raise ValidationError({"quantity": "Quantity must be a finite decimal."})
    if quantity <= 0:
        raise ValidationError({"quantity": "Quantity must be greater than zero."})
    if quantity.as_tuple().exponent < -3:
        raise ValidationError(
            {"quantity": "Quantity cannot have more than three decimal places."}
        )
    return quantity


def _locked_request(request_id):
    return (
        MaterialRequest.all_objects.select_for_update()
        .select_related("project", "material")
        .get(pk=request_id, is_active=True)
    )


def _transition_request(request_id, target_status):
    material_request = _locked_request(request_id)
    allowed_targets = REQUEST_TRANSITIONS.get(material_request.status, set())
    if target_status not in allowed_targets:
        raise ValidationError(
            {
                "status": (
                    f"Material request cannot transition from "
                    f"'{material_request.status}' to '{target_status}'."
                )
            }
        )

    if not material_request.project.is_active or not material_request.material.is_active:
        raise ValidationError(
            {"material": "Material request transitions require active parents."}
        )

    material_request.status = target_status
    material_request.full_clean()
    material_request.save(update_fields=["status", "updated_at"])
    return material_request


@transaction.atomic
def review_material_request(request_id):
    return _transition_request(request_id, MaterialRequest.Status.REVIEWED)


@transaction.atomic
def approve_material_request(request_id, *, actor):
    material_request = _locked_request(request_id)
    if actor is None or not getattr(actor, "pk", None):
        raise ValidationError({"actor": "An approving user is required."})
    if not actor.is_active:
        raise ValidationError({"actor": "The approving user must be active."})
    if material_request.created_by_id == actor.pk:
        raise ValidationError({"actor": "A requester cannot approve their own request."})
    return _transition_request(request_id, MaterialRequest.Status.APPROVED)


@transaction.atomic
def reject_material_request(request_id):
    return _transition_request(request_id, MaterialRequest.Status.REJECTED)


@transaction.atomic
def fulfill_material_request(request_id):
    return _transition_request(request_id, MaterialRequest.Status.COMPLETED)


@transaction.atomic
def consume_material(*, material_id, quantity, actor, usage_date=None, phase=None):
    quantity = _as_material_quantity(quantity)
    if actor is None or not getattr(actor, "pk", None):
        raise ValidationError({"actor": "A consumption author is required."})
    if not actor.is_active:
        raise ValidationError({"actor": "The consumption author must be active."})

    material = (
        Material.all_objects.select_for_update()
        .select_related("project")
        .get(pk=material_id, is_active=True)
    )
    if not material.project.is_active:
        raise ValidationError({"material": "Consumption requires an active project."})
    if quantity > material.quantity_remaining:
        raise ValidationError(
            {"quantity": "Consumption cannot exceed the remaining quantity."}
        )

    material.quantity_used += quantity
    material.quantity_remaining -= quantity
    material.full_clean()
    material.save(
        update_fields=["quantity_used", "quantity_remaining", "updated_at"]
    )

    record = MaterialConsumptionRecord(
        material=material,
        quantity_used=quantity,
        phase=phase,
        created_by=actor,
    )
    if usage_date is not None:
        record.usage_date = usage_date
    record.full_clean()
    record.save()
    return record
