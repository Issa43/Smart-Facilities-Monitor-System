from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.common.models import BaseModel


ASSET_STATUS_VALUES = ("operational", "under_maintenance", "out_of_service")


class Asset(BaseModel):
    class Status(models.TextChoices):
        OPERATIONAL = "operational", "Operational"
        UNDER_MAINTENANCE = "under_maintenance", "Under Maintenance"
        OUT_OF_SERVICE = "out_of_service", "Out Of Service"

    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.PROTECT,
        related_name="assets",
    )
    name = models.CharField(max_length=255)
    asset_type = models.CharField(max_length=100)
    category = models.CharField(max_length=100)
    serial_number = models.CharField(max_length=100, unique=True)
    manufacturer = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    location_inside_facility = models.CharField(max_length=255)
    installation_date = models.DateField()
    operation_date = models.DateField(null=True, blank=True)
    current_status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPERATIONAL,
    )
    health_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("100.00"),
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(Decimal("100")),
        ],
    )
    remaining_useful_life = models.PositiveIntegerField(null=True, blank=True)
    last_maintenance_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["facility"], name="asset_facility_idx"),
            models.Index(fields=["current_status"], name="asset_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(current_status__in=ASSET_STATUS_VALUES),
                name="asset_status_valid",
            ),
            models.CheckConstraint(
                check=Q(health_score__gte=0, health_score__lte=100),
                name="asset_health_score_range",
            ),
            models.CheckConstraint(
                check=(
                    Q(remaining_useful_life__isnull=True)
                    | Q(remaining_useful_life__gte=0)
                ),
                name="asset_rul_nonnegative",
            ),
            models.CheckConstraint(
                check=(
                    Q(operation_date__isnull=True)
                    | Q(operation_date__gte=F("installation_date"))
                ),
                name="asset_operation_after_install",
            ),
            models.CheckConstraint(
                check=(
                    Q(last_maintenance_date__isnull=True)
                    | Q(last_maintenance_date__gte=F("installation_date"))
                ),
                name="asset_maintenance_after_install",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.facility_id and not self.facility.is_active:
            errors["facility"] = "Assets require an active facility."
        if (
            self.installation_date
            and self.operation_date
            and self.operation_date < self.installation_date
        ):
            errors["operation_date"] = (
                "Operation date cannot precede installation date."
            )
        if (
            self.installation_date
            and self.last_maintenance_date
            and self.last_maintenance_date < self.installation_date
        ):
            errors["last_maintenance_date"] = (
                "Last maintenance date cannot precede installation date."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.name} ({self.serial_number})"
