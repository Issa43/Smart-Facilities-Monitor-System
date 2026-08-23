from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.assets.models import Asset
from apps.assets.services import restore_asset_if_clear, transition_asset_status

from .models import Fault, MaintenanceOrder, MaintenanceTask


def _locked_order(order_id):
    return (
        MaintenanceOrder.all_objects.select_for_update()
        .select_related("asset", "asset__facility")
        .get(pk=order_id, is_active=True)
    )


def _locked_fault(fault_id):
    return (
        Fault.all_objects.select_for_update()
        .select_related("asset", "asset__facility")
        .get(pk=fault_id, is_active=True)
    )


def _validate_active_asset(asset):
    if not asset.is_active or not asset.facility.is_active:
        raise ValidationError(
            {"asset": "The asset and its facility must both be active."}
        )


def _mark_asset_under_maintenance(asset):
    if asset.current_status == Asset.Status.OPERATIONAL:
        transition_asset_status(
            asset_id=asset.pk,
            target_status=Asset.Status.UNDER_MAINTENANCE,
        )


@transaction.atomic
def start_maintenance_order(*, order_id):
    order = _locked_order(order_id)
    _validate_active_asset(order.asset)
    if order.status not in {
        MaintenanceOrder.Status.OPEN,
        MaintenanceOrder.Status.ASSIGNED,
    }:
        raise ValidationError(
            {"status": "Only an open or assigned order can enter progress."}
        )

    order.status = MaintenanceOrder.Status.IN_PROGRESS
    order.full_clean()
    order.save(update_fields=["status", "updated_at"])
    _mark_asset_under_maintenance(order.asset)
    return order


@transaction.atomic
def complete_maintenance_order(*, order_id, actual_completion_date):
    order = _locked_order(order_id)
    _validate_active_asset(order.asset)
    if order.status != MaintenanceOrder.Status.IN_PROGRESS:
        raise ValidationError(
            {"status": "Only an in-progress order can be completed."}
        )
    if not isinstance(actual_completion_date, date):
        raise ValidationError(
            {"actual_completion_date": "A valid completion date is required."}
        )

    order.actual_completion_date = actual_completion_date
    order.status = MaintenanceOrder.Status.COMPLETED
    order.full_clean()
    order.save(
        update_fields=["actual_completion_date", "status", "updated_at"]
    )
    return order


@transaction.atomic
def close_maintenance_order(*, order_id):
    order = _locked_order(order_id)
    _validate_active_asset(order.asset)
    if order.status != MaintenanceOrder.Status.COMPLETED:
        raise ValidationError(
            {"status": "Only a completed maintenance order can be closed."}
        )
    if order.actual_completion_date is None:
        raise ValidationError(
            {"actual_completion_date": "An incomplete order cannot be closed."}
        )

    order.status = MaintenanceOrder.Status.CLOSED
    order.full_clean()
    order.save(update_fields=["status", "updated_at"])
    restore_asset_if_clear(asset_id=order.asset_id)
    return order


@transaction.atomic
def cancel_maintenance_order(*, order_id, actor, reason):
    order = _locked_order(order_id)
    if order.status not in {MaintenanceOrder.Status.OPEN, MaintenanceOrder.Status.ASSIGNED}:
        raise ValidationError({"status": "Only an open or assigned order can be cancelled."})
    if not (reason or "").strip():
        raise ValidationError({"cancellation_reason": "A cancellation reason is required."})
    order.status = MaintenanceOrder.Status.CANCELLED
    order.cancelled_by = actor
    order.cancelled_at = timezone.now()
    order.cancellation_reason = reason.strip()
    order.full_clean()
    order.save(update_fields=["status", "cancelled_by", "cancelled_at", "cancellation_reason", "updated_at"])
    restore_asset_if_clear(asset_id=order.asset_id)
    return order


@transaction.atomic
def set_maintenance_execution_notes(*, order_id, notes):
    order = _locked_order(order_id)
    if order.status in {MaintenanceOrder.Status.CLOSED, MaintenanceOrder.Status.CANCELLED}:
        raise ValidationError({"status": "Closed or cancelled orders cannot be edited."})
    order.execution_notes = notes or ""
    order.save(update_fields=["execution_notes", "updated_at"])
    return order


@transaction.atomic
def set_maintenance_task_completion(*, order_id, task_id, actor, completed):
    order = _locked_order(order_id)
    if order.status not in {MaintenanceOrder.Status.ASSIGNED, MaintenanceOrder.Status.IN_PROGRESS}:
        raise ValidationError({"status": "Tasks can only be updated on assigned or in-progress orders."})
    task = MaintenanceTask.all_objects.select_for_update().get(pk=task_id, order=order, is_active=True)
    task.completed_at = timezone.now() if completed else None
    task.completed_by = actor if completed else None
    task.save(update_fields=["completed_at", "completed_by", "updated_at"])
    return task


@transaction.atomic
def begin_fault_investigation(*, fault_id, assigned_engineer=None):
    fault = _locked_fault(fault_id)
    _validate_active_asset(fault.asset)
    if fault.status != Fault.Status.REPORTED:
        raise ValidationError(
            {"status": "Only a reported fault can enter investigation."}
        )

    update_fields = ["status", "updated_at"]
    fault.status = Fault.Status.INVESTIGATING
    if assigned_engineer is not None:
        if not getattr(assigned_engineer, "pk", None) or not assigned_engineer.is_active:
            raise ValidationError(
                {"assigned_engineer": "The assigned engineer must be active."}
            )
        fault.assigned_engineer = assigned_engineer
        update_fields.append("assigned_engineer")

    fault.full_clean()
    fault.save(update_fields=update_fields)
    _mark_asset_under_maintenance(fault.asset)
    return fault


@transaction.atomic
def resolve_fault(*, fault_id, root_cause, resolution):
    fault = _locked_fault(fault_id)
    _validate_active_asset(fault.asset)
    if fault.status != Fault.Status.INVESTIGATING:
        raise ValidationError(
            {"status": "Only a fault under investigation can be resolved."}
        )
    if not (root_cause or "").strip():
        raise ValidationError({"root_cause": "A root cause is required."})
    if not (resolution or "").strip():
        raise ValidationError({"resolution": "A resolution is required."})

    fault.root_cause = root_cause
    fault.resolution = resolution
    fault.resolved_at = timezone.now()
    fault.status = Fault.Status.RESOLVED
    fault.full_clean()
    fault.save(
        update_fields=["root_cause", "resolution", "resolved_at", "status", "updated_at"]
    )
    return fault


@transaction.atomic
def close_fault(*, fault_id):
    fault = _locked_fault(fault_id)
    _validate_active_asset(fault.asset)
    if fault.status != Fault.Status.RESOLVED:
        raise ValidationError(
            {"status": "Only a resolved fault can be closed."}
        )
    if not (fault.root_cause or "").strip() or not (fault.resolution or "").strip():
        raise ValidationError(
            {"resolution": "Fault closure requires a root cause and resolution."}
        )

    fault.status = Fault.Status.CLOSED
    fault.full_clean()
    fault.save(update_fields=["status", "updated_at"])
    restore_asset_if_clear(asset_id=fault.asset_id)
    return fault
