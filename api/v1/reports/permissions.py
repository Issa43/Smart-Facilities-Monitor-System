from uuid import UUID

from rest_framework.permissions import BasePermission

from apps.facilities.models import FacilityAssignment
from apps.projects.models import ProjectAssignment
from apps.reports.models import Report
from apps.users.models import Role, User
from apps.users.permissions import user_has_permission


ROLE_REPORT_MODULES = {
    Role.CONSTRUCTION_MANAGER: {Report.Module.CONSTRUCTION},
    Role.OPERATIONS_MANAGER: {
        Report.Module.ASSETS,
        Report.Module.MAINTENANCE,
        Report.Module.FAULTS,
        Report.Module.OPERATIONAL_PERFORMANCE,
    },
    Role.SECURITY_OFFICER: {
        Report.Module.SECURITY,
        Report.Module.ALERTS,
        Report.Module.RESPONSE,
    },
}


def report_modules_for_user(user):
    """Return the frozen report-module scope for an active API user."""

    if not (
        user
        and user.is_authenticated
        and user.status == User.STATUS_ACTIVE
        and user.role_id
    ):
        return set()
    if user.role.name == Role.SUPER_ADMIN:
        return set(Report.Module.values)
    return set(ROLE_REPORT_MODULES.get(user.role.name, set()))


def has_report_object_scope(user, module, parameters):
    """Enforce Assignment scope before a role can queue a domain report."""

    if user.role.name == Role.SUPER_ADMIN:
        return True
    if user.role.name == Role.CONSTRUCTION_MANAGER:
        project_id = parameters.get("project_id")
        try:
            project_id = UUID(str(project_id))
        except (TypeError, ValueError, AttributeError):
            return False
        return bool(
            project_id
            and ProjectAssignment.objects.filter(
                project_id=project_id,
                project__is_active=True,
                user=user,
                is_active=True,
            ).exists()
        )
    facility_id = parameters.get("facility_id")
    try:
        facility_id = UUID(str(facility_id))
    except (TypeError, ValueError, AttributeError):
        return False
    return bool(
        facility_id
        and FacilityAssignment.objects.filter(
            facility_id=facility_id,
            facility__is_active=True,
            user=user,
            is_active=True,
        ).exists()
    )


class CanUseReports(BasePermission):
    message = "This account is not authorized to use Reports."

    def has_permission(self, request, view):
        return bool(
            report_modules_for_user(request.user)
            and user_has_permission(request.user, "report.generate")
        )

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.role.name == Role.SUPER_ADMIN:
            return True
        if obj.module not in report_modules_for_user(user):
            return False
        if isinstance(obj, Report):
            return obj.created_by_id == user.pk
        return True


class CanManageReportTemplates(BasePermission):
    message = "Only Super Admin can create or update report templates."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.status == User.STATUS_ACTIVE
            and user.role_id
            and user.role.name == Role.SUPER_ADMIN
        )

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)
