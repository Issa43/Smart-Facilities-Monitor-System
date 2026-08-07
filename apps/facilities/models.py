from django.db import models
from django.db.models import Q

from apps.common.models import BaseModel


FACILITY_TYPE_VALUES = (
    "commercial",
    "residential",
    "industrial",
    "healthcare",
    "education",
    "government",
    "mixed_use",
    "other",
)
FACILITY_STATUS_VALUES = (
    "operational",
    "under_maintenance",
    "decommissioned",
)


class Facility(BaseModel):
    class Type(models.TextChoices):
        COMMERCIAL = "commercial", "Commercial"
        RESIDENTIAL = "residential", "Residential"
        INDUSTRIAL = "industrial", "Industrial"
        HEALTHCARE = "healthcare", "Healthcare"
        EDUCATION = "education", "Education"
        GOVERNMENT = "government", "Government"
        MIXED_USE = "mixed_use", "Mixed use"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPERATIONAL = "operational", "Operational"
        UNDER_MAINTENANCE = "under_maintenance", "Under Maintenance"
        DECOMMISSIONED = "decommissioned", "Decommissioned"

    created_from_project = models.OneToOneField(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_facility",
    )
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=Type.choices)
    location = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPERATIONAL,
    )

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(fields=["status"], name="facility_status_idx"),
            models.Index(fields=["type"], name="facility_type_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(type__in=FACILITY_TYPE_VALUES),
                name="facility_type_valid",
            ),
            models.CheckConstraint(
                check=Q(status__in=FACILITY_STATUS_VALUES),
                name="facility_status_valid",
            ),
        ]

    def __str__(self):
        return self.name
