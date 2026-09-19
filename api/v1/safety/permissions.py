"""Authorization and server-side scoping for the Safety REST API.

The scope rule mirrors ``apps.safety.recipients.user_in_alert_scope`` so the
API, notifications, and workflow services agree on who is responsible:

* Super Admin: every project.
* Construction Manager: projects with the user's active ProjectAssignment.
* Operations Manager: projects whose facility is active and has the user's
  active FacilityAssignment.
* Every other role (including Security Officer): nothing.

Scope is always derived from the authenticated user, never from request
parameters.
"""

from rest_framework.permissions import BasePermission

from apps.facilities.models import FacilityAssignment
from apps.projects.models import Project, ProjectAssignment
from apps.safety.models import HazardEvent, ProjectSafetyAlert
from apps.safety.recipients import SAFETY_MANAGE_PERMISSION, SAFETY_VIEW_PERMISSION
from apps.users.models import Role, User
from apps.users.permissions import user_has_permission, view_permission_required


SAFETY_API_ROLES = frozenset({Role.SUPER_ADMIN, Role.CONSTRUCTION_MANAGER, Role.OPERATIONS_MANAGER})


def _is_active_human(user):
    return bool(
        user
        and user.is_authenticated
        and user.status == User.STATUS_ACTIVE
        and user.role_id
    )


class CanUseSafetyAlerts(BasePermission):
    """Active human Super Admin, Construction Manager, or Operations Manager
    holding ``safety.view``, plus any action-specific permission."""

    message = "This account is not authorized to use Safety alerts."

    def has_permission(self, request, view):
        user = request.user
        if not _is_active_human(user) or user.role.name not in SAFETY_API_ROLES:
            return False
        if not user_has_permission(user, SAFETY_VIEW_PERMISSION):
            return False
        required = view_permission_required(view)
        return not required or user_has_permission(user, required)


def user_can_manage_safety(user):
    return _is_active_human(user) and user_has_permission(user, SAFETY_MANAGE_PERMISSION)


def scoped_projects(user):
    """Active projects the user is responsible for."""

    if not _is_active_human(user):
        return Project.objects.none()
    role_name = user.role.name
    if role_name == Role.SUPER_ADMIN:
        return Project.objects.all()
    if role_name == Role.CONSTRUCTION_MANAGER:
        return Project.objects.filter(
            pk__in=ProjectAssignment.objects.filter(user=user, is_active=True).values("project_id")
        )
    if role_name == Role.OPERATIONS_MANAGER:
        return Project.objects.filter(
            facility_id__in=FacilityAssignment.objects.filter(
                user=user,
                is_active=True,
                facility__is_active=True,
            ).values("facility_id")
        )
    return Project.objects.none()


def safety_alerts_for_user(user):
    if not _is_active_human(user):
        return ProjectSafetyAlert.objects.none()
    if user.role.name == Role.SUPER_ADMIN:
        return ProjectSafetyAlert.objects.all()
    return ProjectSafetyAlert.objects.filter(project__in=scoped_projects(user))


def safety_proposals_for_user(user):
    """Proposals on alerts the user is already entitled to see.

    Derived from the alert scope rather than from authorship, so a General
    Manager sees every pending ask while a manager sees the ones raised on
    their own projects -- including a colleague's, which is what makes the
    decision visible to the people responsible for the site.
    """

    from apps.safety.models import SafetyActionProposal

    if not _is_active_human(user):
        return SafetyActionProposal.objects.none()
    return SafetyActionProposal.objects.filter(alert__in=safety_alerts_for_user(user))


def hazard_events_for_user(user):
    """Super Admin sees every stored event; managers see events that produced
    an alert for one of their scoped projects."""

    if not _is_active_human(user):
        return HazardEvent.objects.none()
    if user.role.name == Role.SUPER_ADMIN:
        return HazardEvent.objects.all()
    return HazardEvent.objects.filter(
        pk__in=safety_alerts_for_user(user).values("hazard_event_id")
    )
