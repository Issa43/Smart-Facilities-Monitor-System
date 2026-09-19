from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Asset


ASSET_STATUS_TRANSITIONS = {
    Asset.Status.OPERATIONAL: {
        Asset.Status.UNDER_MAINTENANCE,
        Asset.Status.OUT_OF_SERVICE,
    },
    Asset.Status.UNDER_MAINTENANCE: {
        Asset.Status.OPERATIONAL,
        Asset.Status.OUT_OF_SERVICE,
    },
    Asset.Status.OUT_OF_SERVICE: {Asset.Status.UNDER_MAINTENANCE},
}


def _has_operational_blockers(asset):
    from apps.maintenance.models import Fault, MaintenanceOrder

    blocking_orders = MaintenanceOrder.objects.filter(
        asset=asset,
        status__in=(
            MaintenanceOrder.Status.IN_PROGRESS,
            MaintenanceOrder.Status.COMPLETED,
        ),
    ).exists()
    blocking_faults = Fault.objects.filter(
        asset=asset,
        status__in=(
            Fault.Status.REPORTED,
            Fault.Status.INVESTIGATING,
            Fault.Status.RESOLVED,
        ),
    ).exists()
    return blocking_orders or blocking_faults


@transaction.atomic
def transition_asset_status(*, asset_id, target_status):
    asset = (
        Asset.all_objects.select_for_update()
        .select_related("facility")
        .get(pk=asset_id, is_active=True)
    )
    allowed_targets = ASSET_STATUS_TRANSITIONS.get(asset.current_status, set())
    if target_status not in allowed_targets:
        raise ValidationError(
            {
                "current_status": (
                    f"Asset cannot transition from '{asset.current_status}' "
                    f"to '{target_status}'."
                )
            }
        )
    if target_status == Asset.Status.OPERATIONAL and _has_operational_blockers(asset):
        raise ValidationError(
            {
                "current_status": (
                    "Asset cannot become operational while maintenance or faults "
                    "remain unresolved."
                )
            }
        )

    asset.current_status = target_status
    asset.full_clean()
    asset.save(update_fields=["current_status", "updated_at"])
    return asset


@transaction.atomic
def restore_asset_if_clear(*, asset_id):
    asset = (
        Asset.all_objects.select_for_update()
        .select_related("facility")
        .get(pk=asset_id, is_active=True)
    )
    if asset.current_status != Asset.Status.UNDER_MAINTENANCE:
        return asset
    if _has_operational_blockers(asset):
        return asset
    return transition_asset_status(
        asset_id=asset.pk,
        target_status=Asset.Status.OPERATIONAL,
    )
