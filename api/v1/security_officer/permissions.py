from rest_framework.permissions import BasePermission

from apps.attachments.models import Attachment
from apps.attachments.registry import (
    AttachmentEntityRegistry,
    AttachmentEntityRegistryError,
)
from apps.facilities.models import Facility, FacilityAssignment
from apps.users.models import Role, User
from apps.users.permissions import user_has_permission, view_permission_required


class IsSecurityOfficerOrSuperAdmin(BasePermission):
    """Require an active Security Officer or the Super Admin bypass."""

    message = "This action is restricted to Security Officers."

    def has_permission(self, request, view):
        user = request.user
        role_allowed = bool(
            user
            and user.is_authenticated
            and user.status == User.STATUS_ACTIVE
            and user.role_id
            and user.role.name in {Role.SECURITY_OFFICER, Role.SUPER_ADMIN}
        )
        permission = view_permission_required(view)
        return role_allowed and (not permission or user_has_permission(user, permission))

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.role.name == Role.SUPER_ADMIN:
            return True
        facility_id = _facility_id_for_object(obj)
        return bool(
            facility_id
            and FacilityAssignment.objects.filter(
                facility_id=facility_id,
                user=user,
                is_active=True,
            ).exists()
        )


def _facility_id_for_object(obj):
    if isinstance(obj, Facility):
        return obj.pk
    if isinstance(obj, Attachment):
        try:
            entity = AttachmentEntityRegistry.resolve(obj.entity_type, obj.entity_id)
            return AttachmentEntityRegistry.resolve_facility(
                obj.entity_type,
                entity,
            ).pk
        except (AttachmentEntityRegistryError, AttributeError):
            return None
    if hasattr(obj, "facility_id"):
        return obj.facility_id
    if hasattr(obj, "incident"):
        return obj.incident.facility_id
    return None


def facilities_for_security_user(user):
    """Return active Facilities in the authenticated Security Officer's scope."""

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
    if user.role.name != Role.SECURITY_OFFICER:
        return queryset.none()
    return queryset.filter(
        assignments__user=user,
        assignments__is_active=True,
    ).distinct()


def user_has_active_facility_assignment(user, facility, *, role_name):
    return bool(
        user
        and user.status == User.STATUS_ACTIVE
        and user.role_id
        and user.role.name == role_name
        and FacilityAssignment.objects.filter(
            facility=facility,
            user=user,
            is_active=True,
        ).exists()
    )
