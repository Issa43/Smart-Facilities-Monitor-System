from rest_framework.permissions import BasePermission, SAFE_METHODS

from apps.users.models import Role


PERMISSION_CATALOG = {
    "project.create", "project.edit", "project.view", "project.close",
    "stage.create", "stage.edit", "stage.delete", "stage.progress", "stage.approve",
    "material.manage", "material.request", "material.stock",
    "asset.manage", "asset.status", "workorder.create", "workorder.close",
    "fault.manage", "alert.view", "incident.create", "incident.update",
    "incident.close", "incident.escalate", "report.generate", "report.all",
    "user.manage", "role.manage", "audit.view", "settings.manage",
}


def user_has_permission(user, permission_name):
    """Evaluate persisted SFLMS permissions; Super Admin remains a break-glass role."""
    if not (user and user.is_authenticated and user.role_id and user.is_active):
        return False
    if user.role.name == Role.SUPER_ADMIN:
        return True
    return user.role.permissions.filter(permission_name=permission_name).exists()


def view_permission_required(view):
    requirement = getattr(view, "permission_required", None)
    if isinstance(requirement, dict):
        return requirement.get(getattr(view, "action", None), requirement.get("default"))
    return requirement


class IsSuperAdminForWrite(BasePermission):
    """
    Users & Roles management is Super Admin only (architecture §6 permission
    matrix: "Users/Roles -> Full CRUD: Super Admin only, no access otherwise").
    Any authenticated user may read their own profile via the `me` action,
    which is handled separately in the view (not through this class).
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return bool(user.role_id and user.is_active)
        return bool(user.role_id and user.role.name == Role.SUPER_ADMIN)
