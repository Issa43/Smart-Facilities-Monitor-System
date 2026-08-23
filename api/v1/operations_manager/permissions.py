from rest_framework.permissions import BasePermission

from apps.facilities.models import Facility
from apps.users.models import Role, User
from apps.users.permissions import user_has_permission, view_permission_required


class IsOperationsManagerOrSuperAdmin(BasePermission):
    """Allow active Operations Managers and the global Super Admin bypass."""

    message = "This action is restricted to Operations Managers."

    def has_permission(self, request, view):
        user = request.user
        role_allowed = bool(
            user
            and user.is_authenticated
            and user.status == User.STATUS_ACTIVE
            and user.role_id
            and user.role.name in {Role.OPERATIONS_MANAGER, Role.SUPER_ADMIN}
        )
        permission = view_permission_required(view)
        return role_allowed and (not permission or user_has_permission(user, permission))


def facilities_for_user(user):
    """Return active Facilities visible through the approved RBAC scope."""

    queryset = Facility.objects.all()
    if not (
        user
        and user.is_authenticated
        and user.status == User.STATUS_ACTIVE
        and user.role_id
    ):
        return queryset.none()
    if user.role.name == Role.SUPER_ADMIN:
        return queryset
    return queryset.filter(
        assignments__user=user,
        assignments__is_active=True,
    ).distinct()
