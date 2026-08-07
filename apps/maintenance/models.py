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
)
FAULT_SEVERITY_VALUES = ("minor", "moderate", "major", "critical")
FAULT_STATUS_VALUES = ("reported", "investigating", "resolved", "closed")


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
        ]

    def clean(self):
        super().clean()
        if self.asset_id and (
            not self.asset.is_active or not self.asset.facility.is_active
        ):
            raise ValidationError(
                {"asset": "Maintenance orders require an active asset and facility."}
            )

    def __str__(self):
        return f"{self.asset} - {self.get_type_display()}"


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

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.asset} - {self.fault_type}"
