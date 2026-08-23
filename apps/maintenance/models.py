import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.common.models import BaseModel


MAINTENANCE_TYPE_VALUES = ("preventive", "corrective", "emergency")
MAINTENANCE_PRIORITY_VALUES = ("low", "medium", "high", "urgent")
MAINTENANCE_STATUS_VALUES = (
    "open",
    "assigned",
    "in_progress",
    "completed",
    "closed",
    "cancelled",
)
FAULT_SEVERITY_VALUES = ("minor", "moderate", "major", "critical")
FAULT_STATUS_VALUES = ("reported", "investigating", "resolved", "closed")


def generate_maintenance_reference():
    return f"WO-{uuid.uuid4().hex[:12].upper()}"


class MaintenanceOrder(BaseModel):
    class Type(models.TextChoices):
        PREVENTIVE = "preventive", "Preventive"
        CORRECTIVE = "corrective", "Corrective"
        EMERGENCY = "emergency", "Emergency"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CLOSED = "closed", "Closed"
        CANCELLED = "cancelled", "Cancelled"

    reference = models.CharField(max_length=20, unique=True, default=generate_maintenance_reference, editable=False)

    asset = models.ForeignKey(
        "assets.Asset",
        on_delete=models.PROTECT,
        related_name="maintenance_orders",
    )
    type = models.CharField(max_length=20, choices=Type.choices)
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    description = models.TextField()
    reason = models.TextField()
    assigned_to = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_maintenance_orders",
    )
    expected_execution_date = models.DateField()
    actual_completion_date = models.DateField(null=True, blank=True)
    execution_notes = models.TextField(blank=True, default="")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        "users.User", null=True, blank=True, on_delete=models.PROTECT, related_name="cancelled_maintenance_orders"
    )
    cancellation_reason = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["asset", "status"],
                name="maint_order_asset_status_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(type__in=MAINTENANCE_TYPE_VALUES),
                name="maintenance_order_type_valid",
            ),
            models.CheckConstraint(
                check=Q(priority__in=MAINTENANCE_PRIORITY_VALUES),
                name="maintenance_order_priority_valid",
            ),
            models.CheckConstraint(
                check=Q(status__in=MAINTENANCE_STATUS_VALUES),
                name="maintenance_order_status_valid",
            ),
            models.CheckConstraint(
                check=(
                    ~Q(status__in=("completed", "closed"))
                    | Q(actual_completion_date__isnull=False)
                ),
                name="maintenance_completed_has_date",
            ),
            models.CheckConstraint(
                check=(
                    (
                        Q(status="cancelled")
                        & Q(cancelled_at__isnull=False)
                        & Q(cancelled_by__isnull=False)
                        & ~Q(cancellation_reason="")
                    )
                    | (
                        ~Q(status="cancelled")
                        & Q(cancelled_at__isnull=True)
                        & Q(cancelled_by__isnull=True)
                        & Q(cancellation_reason="")
                    )
                ),
                name="maintenance_cancellation_fields_valid",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.asset_id and (
            not self.asset.is_active or not self.asset.facility.is_active
        ):
            errors["asset"] = "Maintenance orders require an active asset and facility."
        if self.status in {self.Status.COMPLETED, self.Status.CLOSED} and not self.actual_completion_date:
            errors["actual_completion_date"] = "Completed orders require a completion date."
        cancellation_fields = bool(self.cancelled_at) and bool(self.cancelled_by_id) and bool((self.cancellation_reason or "").strip())
        if self.status == self.Status.CANCELLED and not cancellation_fields:
            errors["cancellation_reason"] = "Cancelled orders require an actor, timestamp, and reason."
        elif self.status != self.Status.CANCELLED and (self.cancelled_at or self.cancelled_by_id or self.cancellation_reason):
            errors["cancelled_at"] = "Cancellation fields are only valid for cancelled orders."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.reference


class MaintenanceTask(BaseModel):
    order = models.ForeignKey(MaintenanceOrder, on_delete=models.PROTECT, related_name="tasks")
    sequence = models.PositiveIntegerField()
    label = models.CharField(max_length=255)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey("users.User", null=True, blank=True, on_delete=models.PROTECT, related_name="completed_maintenance_tasks")

    class Meta(BaseModel.Meta):
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(fields=["order", "sequence"], name="unique_maintenance_task_sequence"),
            models.CheckConstraint(
                check=(
                    (Q(completed_at__isnull=True) & Q(completed_by__isnull=True))
                    | (Q(completed_at__isnull=False) & Q(completed_by__isnull=False))
                ),
                name="maintenance_task_completion_fields_valid",
            ),
        ]
        indexes = [models.Index(fields=["order", "sequence"], name="maint_task_order_seq_idx")]


class Fault(BaseModel):
    class Severity(models.TextChoices):
        MINOR = "minor", "Minor"
        MODERATE = "moderate", "Moderate"
        MAJOR = "major", "Major"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        REPORTED = "reported", "Reported"
        INVESTIGATING = "investigating", "Investigating"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    asset = models.ForeignKey(
        "assets.Asset",
        on_delete=models.PROTECT,
        related_name="faults",
    )
    fault_type = models.CharField(max_length=100)
    description = models.TextField()
    severity = models.CharField(max_length=10, choices=Severity.choices)
    discovery_time = models.DateTimeField(default=timezone.now)
    reported_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reported_faults",
    )
    assigned_engineer = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_faults",
    )
    root_cause = models.TextField(null=True, blank=True)
    resolution = models.TextField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.REPORTED,
    )

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["asset", "status"],
                name="fault_asset_status_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(severity__in=FAULT_SEVERITY_VALUES),
                name="fault_severity_valid",
            ),
            models.CheckConstraint(
                check=Q(status__in=FAULT_STATUS_VALUES),
                name="fault_status_valid",
            ),
            models.CheckConstraint(
                check=(
                    ~Q(status__in=("resolved", "closed"))
                    | (
                        Q(root_cause__isnull=False)
                        & ~Q(root_cause="")
                        & Q(resolution__isnull=False)
                        & ~Q(resolution="")
                        & Q(resolved_at__isnull=False)
                    )
                ),
                name="fault_resolution_fields_valid",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.asset_id and (
            not self.asset.is_active or not self.asset.facility.is_active
        ):
            errors["asset"] = "Faults require an active asset and facility."
        if self._state.adding and not self.reported_by_id:
            errors["reported_by"] = "A fault reporter is required."
        if self.status in {self.Status.RESOLVED, self.Status.CLOSED} and (
            not (self.root_cause or "").strip()
            or not (self.resolution or "").strip()
            or not self.resolved_at
        ):
            errors["resolution"] = "Resolved faults require root cause, resolution, and timestamp."

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.asset} - {self.fault_type}"
