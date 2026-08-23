from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.common.models import BaseModel
from apps.users.models import Role


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
FACILITY_ASSIGNMENT_ROLE_VALUES = (
    "operations_manager",
    "security_officer",
    "viewer",
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
    operation_start_date = models.DateField(null=True, blank=True)
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


class FacilityAssignment(BaseModel):
    class RoleType(models.TextChoices):
        OPERATIONS_MANAGER = "operations_manager", "Operations manager"
        SECURITY_OFFICER = "security_officer", "Security officer"
        VIEWER = "viewer", "Viewer"

    facility = models.ForeignKey(
        Facility,
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    user = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        related_name="facility_assignments",
    )
    role_type = models.CharField(max_length=20, choices=RoleType.choices)

    class Meta(BaseModel.Meta):
        indexes = [
            models.Index(
                fields=["user", "facility"],
                name="facility_assign_user_fac_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "user", "role_type"],
                name="unique_facility_user_role_assignment",
            ),
            models.CheckConstraint(
                check=Q(role_type__in=FACILITY_ASSIGNMENT_ROLE_VALUES),
                name="facility_assignment_role_valid",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.facility_id and not self.facility.is_active:
            errors["facility"] = "Assignments require an active facility."

        if self.user_id:
            if not self.user.is_active:
                errors["user"] = "Assignments require an active user."
            elif not self.user.role_id:
                errors["user"] = "Assignments require a user role."
            elif (
                self.role_type == self.RoleType.OPERATIONS_MANAGER
                and self.user.role.name != Role.OPERATIONS_MANAGER
            ):
                errors["user"] = (
                    "Operations manager assignments require the Operations "
                    "Manager role."
                )
            elif (
                self.role_type == self.RoleType.SECURITY_OFFICER
                and self.user.role.name != Role.SECURITY_OFFICER
            ):
                errors["user"] = (
                    "Security officer assignments require the Security Officer role."
                )
            elif self.role_type == self.RoleType.VIEWER and self.user.role.name not in {
                Role.OPERATIONS_MANAGER,
                Role.SECURITY_OFFICER,
            }:
                errors["user"] = (
                    "Facility viewers must have an Operations Manager or "
                    "Security Officer role."
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.user} - {self.facility} ({self.get_role_type_display()})"
