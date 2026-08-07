from rest_framework.permissions import BasePermission

from apps.users.models import Role


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
        return bool(user.role_id and user.role.name == Role.SUPER_ADMIN)
