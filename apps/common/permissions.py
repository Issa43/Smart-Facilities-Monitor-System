"""
RBAC foundation (architecture §6).

These base classes only check the *role* of the requesting user
(coarse-grained access). Object-level filtering through
`ProjectAssignment` / `FacilityAssignment` is layered on top of these
in each domain app's own `permissions.py`, starting from Phase 3/4,
once those apps exist.
"""
from rest_framework.permissions import BasePermission

from apps.users.models import Role


class IsAuthenticatedAndActive(BasePermission):
    """Base requirement for every endpoint: authenticated + not suspended."""

    message = "Authentication required or account is inactive."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.status == "active")


class IsSuperAdmin(BasePermission):
    message = "This action is restricted to Super Admin."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.role_id
            and user.role.name == Role.SUPER_ADMIN
        )


class HasRole(BasePermission):
    """
    Factory-style permission: HasRole(Role.CONSTRUCTION_MANAGER, Role.SUPER_ADMIN)
    Usage in a view:  permission_classes = [HasRole(Role.OPERATIONS_MANAGER)]
    """

    def __init__(self, *allowed_roles):
        self.allowed_roles = allowed_roles

    def __call__(self):
        # DRF instantiates permission classes with no args; this makes
        # HasRole(...) usable directly in `permission_classes` lists.
        return self

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.role_id):
            return False
        if user.role.name == Role.SUPER_ADMIN:
            return True  # Super Admin always has full access (architecture §6).
        return user.role.name in self.allowed_roles
