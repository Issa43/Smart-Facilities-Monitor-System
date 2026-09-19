from rest_framework.permissions import BasePermission

from apps.users.models import Role, User
from apps.users.permissions import user_has_permission, view_permission_required


class IsConstructionManagerOrSuperAdmin(BasePermission):
    """Allow active Construction Managers and the global Super Admin bypass."""

    message = "This action is restricted to Construction Managers."

    def has_permission(self, request, view):
        user = request.user
        role_allowed = bool(
            user
            and user.is_authenticated
            and user.status == User.STATUS_ACTIVE
            and user.role_id
            and user.role.name
            in {Role.CONSTRUCTION_MANAGER, Role.SUPER_ADMIN}
        )
        permission = view_permission_required(view)
        return role_allowed and (not permission or user_has_permission(user, permission))
