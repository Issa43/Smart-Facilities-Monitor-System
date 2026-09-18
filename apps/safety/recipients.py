"""Who is responsible for a project safety alert.

A single scope rule serves both notification fan-out and authorization of
human workflow actions, so the two can never drift apart:

* Construction Managers with an active ProjectAssignment on the project.
* Operations Managers with an active FacilityAssignment on the project's
  (active) facility. Projects without a facility have no Operations scope.
* Super Admins, who bypass assignment scope.

Assignment ``role_type`` is intentionally not consulted, matching the
existing Construction and Operations APIs (decision D8).
"""

from dataclasses import dataclass

from apps.facilities.models import Facility, FacilityAssignment
from apps.projects.models import ProjectAssignment
from apps.users.models import Role, User
from apps.users.permissions import user_has_permission


SAFETY_VIEW_PERMISSION = "safety.view"
SAFETY_MANAGE_PERMISSION = "safety.manage"
SAFETY_BROADCAST_PERMISSION = "safety.broadcast"
# The two protective workflows are separate responsibilities with separate
# permissions: the Construction Manager speaks for the project's site
# personnel, the Operations Manager for the facility's equipment. Neither is
# granted the other's, so neither can propose in the other's name.
SAFETY_PROPOSE_WORKER_PERMISSION = "safety.propose_worker_protection"
SAFETY_PROPOSE_ASSET_PERMISSION = "safety.propose_asset_protection"
# Deliberately granted to no role. `user_has_permission` short-circuits to True
# for Super Admin only, so this is the General Manager's approval authority and
# cannot be obtained by any other role without an explicit new grant.
SAFETY_APPROVE_PERMISSION = "safety.approve"
SUPER_ADMIN_NOTIFY_SEVERITIES = frozenset({"high", "critical"})

CONSTRUCTION_ALERT_PATH = "/construction/safety-alerts/{alert_id}"
OPERATIONS_ALERT_PATH = "/operations/safety-alerts/{alert_id}"


@dataclass(frozen=True)
class RecipientGroup:
    users: tuple
    href: str


def _active_facility_id(project):
    if not project.facility_id:
        return None
    return (
        Facility.objects.filter(pk=project.facility_id)
        .values_list("pk", flat=True)
        .first()
    )


def _scoped_role_users(role_name):
    return User.objects.filter(
        status=User.STATUS_ACTIVE,
        role__name=role_name,
        role__permissions__permission_name=SAFETY_VIEW_PERMISSION,
    )


def construction_manager_recipients(project):
    return list(
        _scoped_role_users(Role.CONSTRUCTION_MANAGER)
        .filter(
            project_assignments__project_id=project.pk,
            project_assignments__is_active=True,
        )
        .distinct()
        .order_by("pk")
    )


def operations_manager_recipients(project):
    facility_id = _active_facility_id(project)
    if facility_id is None:
        return []
    return list(
        _scoped_role_users(Role.OPERATIONS_MANAGER)
        .filter(
            facility_assignments__facility_id=facility_id,
            facility_assignments__is_active=True,
        )
        .distinct()
        .order_by("pk")
    )


def super_admin_recipients(severity):
    if severity not in SUPER_ADMIN_NOTIFY_SEVERITIES:
        return []
    return list(
        User.objects.filter(status=User.STATUS_ACTIVE, role__name=Role.SUPER_ADMIN).order_by("pk")
    )


def alert_recipient_groups(alert, *, severity=None):
    """Return recipient groups with their role-specific frontend paths."""

    project = alert.project
    alert_id = alert.pk
    groups = [
        RecipientGroup(
            users=tuple(construction_manager_recipients(project)),
            href=CONSTRUCTION_ALERT_PATH.format(alert_id=alert_id),
        ),
        RecipientGroup(
            users=tuple(operations_manager_recipients(project)),
            href=OPERATIONS_ALERT_PATH.format(alert_id=alert_id),
        ),
        RecipientGroup(
            users=tuple(super_admin_recipients(severity or alert.severity)),
            href=OPERATIONS_ALERT_PATH.format(alert_id=alert_id),
        ),
    ]
    return [group for group in groups if group.users]


def user_in_alert_scope(user, alert):
    """True when an active human user is responsible for the alert's project."""

    if not (
        user
        and getattr(user, "is_authenticated", False)
        and user.is_active
        and user.role_id
    ):
        return False
    role_name = user.role.name
    if role_name == Role.SUPER_ADMIN:
        return True
    project = alert.project
    if role_name == Role.CONSTRUCTION_MANAGER:
        return ProjectAssignment.objects.filter(
            project_id=project.pk,
            project__is_active=True,
            user=user,
            is_active=True,
        ).exists()
    if role_name == Role.OPERATIONS_MANAGER:
        facility_id = _active_facility_id(project)
        return bool(
            facility_id
            and FacilityAssignment.objects.filter(
                facility_id=facility_id,
                user=user,
                is_active=True,
            ).exists()
        )
    return False


def user_can_view_alert(user, alert):
    return user_in_alert_scope(user, alert) and user_has_permission(user, SAFETY_VIEW_PERMISSION)


def user_can_manage_alert(user, alert):
    return (
        user_in_alert_scope(user, alert)
        and user_has_permission(user, SAFETY_VIEW_PERMISSION)
        and user_has_permission(user, SAFETY_MANAGE_PERMISSION)
    )


PROPOSAL_PERMISSION_BY_TYPE = {
    "worker_protection": SAFETY_PROPOSE_WORKER_PERMISSION,
    "asset_protection": SAFETY_PROPOSE_ASSET_PERMISSION,
}


def user_can_approve_safety(user):
    """Approval authority over protective proposals: the General Manager.

    Scope-free by design, matching the existing RBAC model in which Super Admin
    is not assignment-bound. Only the ruling is global; who may *propose*
    remains bound to assignment scope.
    """

    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and user.is_active
        and user.role_id
        and user_has_permission(user, SAFETY_APPROVE_PERMISSION)
    )


def user_can_propose(user, alert, decision_type):
    """True when this user may propose this kind of action on this alert.

    Three independent conditions. The alert must be inside the user's own
    assignment scope; the user must hold the permission specific to that
    workflow, so a Construction Manager cannot propose asset protection and an
    Operations Manager cannot propose worker protection; and the user must not
    be an approver.

    That last one is separation of duties made structural rather than
    procedural. The General Manager rules on proposals and does not raise them,
    so there is no proposal they could be asked to judge their own. It is also
    why the permission check alone is not enough: ``user_has_permission``
    short-circuits to True for Super Admin, which would otherwise hand the
    approver both proposal permissions.
    """

    permission = PROPOSAL_PERMISSION_BY_TYPE.get(decision_type)
    if permission is None:
        return False
    if user_can_approve_safety(user):
        return False
    return (
        user_in_alert_scope(user, alert)
        and user_has_permission(user, SAFETY_VIEW_PERMISSION)
        and user_has_permission(user, permission)
    )


def project_telegram_destinations(project):
    """Enabled Telegram channels for one project, in a stable order.

    Approved worker instructions are addressed to the project, so this is the
    whole routing rule: a project's own destinations and nothing else. A
    project without one resolves to an empty list, which the caller records
    rather than treating as success.
    """

    from .models import ProjectTelegramDestination

    return list(
        ProjectTelegramDestination.objects.filter(
            project_id=project.pk,
            is_enabled=True,
        ).order_by("pk")
    )
