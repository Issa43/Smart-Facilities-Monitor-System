from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.common.models import BaseModel


MATERIAL_UNIT_VALUES = (
    "each",
    "kg",
    "g",
    "tonne",
    "l",
    "ml",
    "m",
    "m2",
    "m3",
    "box",
    "pack",
    "roll",
    "sheet",
    "bag",
)
MATERIAL_REQUEST_PRIORITY_VALUES = ("low", "medium", "high", "urgent")
MATERIAL_REQUEST_STATUS_VALUES = (
    "submitted",
    "reviewed",
    "approved",
    "rejected",
    "completed",
)


class Material(BaseModel):
    class Unit(models.TextChoices):
        EACH = "each", "Each"
        KILOGRAM = "kg", "Kilogram"
        GRAM = "g", "Gram"
        TONNE = "tonne", "Tonne"
        LITRE = "l", "Litre"
        MILLILITRE = "ml", "Millilitre"
        METRE = "m", "Metre"
        SQUARE_METRE = "m2", "Square metre"
        CUBIC_METRE = "m3", "Cubic metre"
        BOX = "box", "Box"
        PACK = "pack", "Pack"
        ROLL = "roll", "Roll"
        SHEET = "sheet", "Sheet"
        BAG = "bag", "Bag"

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        related_name="materials",
    )
    name = models.CharField(max_length=255)
    unit = models.CharField(max_length=10, choices=Unit.choices)
    quantity_required = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0"))],
    )
    quantity_used = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0"))],
    )
    quantity_remaining = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0"))],
    )
    min_stock_threshold = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["project", "name"],
                name="material_project_name_idx",
            ),
            models.Index(
                fields=["project", "quantity_remaining"],
                name="material_project_remaining_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(
                    quantity_required__gte=0,
                    quantity_used__gte=0,
                    quantity_remaining__gte=0,
                    min_stock_threshold__gte=0,
                ),
                name="material_quantities_nonnegative",
            ),
            models.CheckConstraint(
                check=Q(quantity_used__lte=F("quantity_required")),
                name="material_used_within_required",
            ),
            models.CheckConstraint(
                check=Q(
                    quantity_remaining=F("quantity_required") - F("quantity_used")
                ),
                name="material_balance_consistent",
            ),
            models.CheckConstraint(
                check=Q(unit__in=MATERIAL_UNIT_VALUES),
                name="material_unit_valid",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.project_id and not self.project.is_active:
            errors["project"] = "Materials require an active project."

        if (
            self.quantity_used is not None
            and self.quantity_required is not None
            and self.quantity_used > self.quantity_required
        ):
            errors["quantity_used"] = (
                "Quantity used cannot exceed quantity required."
            )

        if (
            self.quantity_required is not None
            and self.quantity_used is not None
            and self.quantity_remaining is not None
            and self.quantity_remaining
            != self.quantity_required - self.quantity_used
        ):
            errors["quantity_remaining"] = (
                "Quantity remaining must equal quantity required minus quantity used."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.project} - {self.name}"


class MaterialRequest(BaseModel):
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        REVIEWED = "reviewed", "Reviewed"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        COMPLETED = "completed", "Completed"

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        related_name="material_requests",
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name="requests",
    )
    quantity_requested = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    reason = models.TextField()
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.SUBMITTED,
    )

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["project", "status"],
                name="mat_req_project_status_idx",
            ),
            models.Index(
                fields=["material", "status"],
                name="mat_req_material_status_idx",
            ),
            models.Index(
                fields=["created_by", "status"],
                name="mat_req_creator_status_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(quantity_requested__gt=0),
                name="material_request_quantity_positive",
            ),
            models.CheckConstraint(
                check=Q(priority__in=MATERIAL_REQUEST_PRIORITY_VALUES),
                name="material_request_priority_valid",
            ),
            models.CheckConstraint(
                check=Q(status__in=MATERIAL_REQUEST_STATUS_VALUES),
                name="material_request_status_valid",
            ),
            models.CheckConstraint(
                check=Q(created_by__isnull=False),
                name="material_request_creator_req",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.project_id and not self.project.is_active:
            errors["project"] = "Material requests require an active project."

        if self.material_id:
            if not self.material.is_active:
                errors["material"] = "Material requests require an active material."
            elif self.project_id and self.material.project_id != self.project_id:
                errors["material"] = (
                    "The selected material must belong to the request project."
                )

        if self._state.adding and not self.created_by_id:
            errors["created_by"] = "A material request creator is required."

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.material} - {self.quantity_requested} {self.material.unit}"


class MaterialConsumptionRecord(BaseModel):
    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name="consumption_records",
    )
    quantity_used = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    usage_date = models.DateField(default=timezone.localdate)
    phase = models.ForeignKey(
        "projects.ProjectPhase",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="material_consumption_records",
    )

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["material", "usage_date"],
                name="mat_consumption_usage_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(quantity_used__gt=0),
                name="material_consumption_positive",
            ),
            models.CheckConstraint(
                check=Q(created_by__isnull=False),
                name="material_consumption_author_req",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.material_id:
            if not self.material.is_active or not self.material.project.is_active:
                errors["material"] = (
                    "Consumption requires an active material and project."
                )
            elif self.phase_id and self.phase.project_id != self.material.project_id:
                errors["phase"] = (
                    "The selected phase must belong to the material project."
                )

        if self.phase_id and not self.phase.is_active:
            errors["phase"] = "Consumption requires an active phase."
        if not self.created_by_id:
            errors["created_by"] = "A consumption author is required."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self._state.adding and self.pk:
            original = self.__class__.all_objects.get(pk=self.pk)
            immutable_fields = (
                "material_id",
                "quantity_used",
                "usage_date",
                "phase_id",
                "created_by_id",
                "created_at",
            )
            changed_fields = [
                field_name
                for field_name in immutable_fields
                if getattr(original, field_name) != getattr(self, field_name)
            ]
            if changed_fields:
                raise ValidationError(
                    "Material consumption history is immutable: "
                    + ", ".join(changed_fields)
                )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Material consumption records cannot be hard-deleted.")

    def __str__(self):
        return f"{self.material} - {self.quantity_used} {self.material.unit}"
