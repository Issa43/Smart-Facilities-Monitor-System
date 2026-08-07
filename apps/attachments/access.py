from django.apps import apps as django_apps

from apps.users.models import Role

from .registry import (
    AttachmentEntityNotFound,
    AttachmentEntityRegistry,
    UnsupportedAttachmentEntityType,
)


class ProtectedAttachmentNotFound(Exception):
    """Raised when an attachment or its active parent cannot be disclosed."""


class ProtectedAttachmentAccessDenied(Exception):
    """Raised when an authenticated user lacks parent-entity access."""


def _require_active_user(user):
    if not (
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
    ):
        raise ProtectedAttachmentAccessDenied("Active authentication is required.")


def _authorize_project_scope(user, project):
    if not getattr(project, "is_active", False):
        raise ProtectedAttachmentNotFound("Protected file parent not found.")
    role_name = getattr(getattr(user, "role", None), "name", None)
    if role_name == Role.SUPER_ADMIN:
        return
    if role_name != Role.CONSTRUCTION_MANAGER:
        raise ProtectedAttachmentAccessDenied("Protected file access is forbidden.")
    assignment_model = django_apps.get_model("projects.ProjectAssignment")
    if not assignment_model.objects.filter(project=project, user=user).exists():
        raise ProtectedAttachmentNotFound("Protected file parent not found.")


def authorize_attachment_download(user, attachment):
    """Authorize access using global role plus active ProjectAssignment scope."""
    if not getattr(attachment, "is_active", False):
        raise ProtectedAttachmentNotFound("Attachment not found.")

    _require_active_user(user)

    try:
        entity = AttachmentEntityRegistry.resolve(
            attachment.entity_type,
            attachment.entity_id,
        )
        project = AttachmentEntityRegistry.resolve_project(
            attachment.entity_type,
            entity,
        )
    except (
        AttachmentEntityNotFound,
        UnsupportedAttachmentEntityType,
        AttributeError,
    ) as exc:
        raise ProtectedAttachmentNotFound("Attachment parent not found.") from exc

    if not getattr(project, "is_active", False):
        raise ProtectedAttachmentNotFound("Attachment parent not found.")

    _authorize_project_scope(user, project)
    return entity


def authorize_protected_file_download(user, instance):
    """Authorize every current protected FileField without exposing its path."""
    _require_active_user(user)
    if not getattr(instance, "is_active", False):
        raise ProtectedAttachmentNotFound("Protected file not found.")

    label = instance._meta.label_lower
    if label == "attachments.attachment":
        authorize_attachment_download(user, instance)
    elif label == "projects.project":
        _authorize_project_scope(user, instance)
    elif label == "projects.projectdocument":
        _authorize_project_scope(user, instance.project)
    elif label == "security.securityalert":
        if not instance.facility.is_active:
            raise ProtectedAttachmentNotFound("Protected file parent not found.")
        role_name = getattr(getattr(user, "role", None), "name", None)
        if role_name not in {Role.SUPER_ADMIN, Role.SECURITY_OFFICER}:
            raise ProtectedAttachmentAccessDenied("Protected file access is forbidden.")
    elif label == "reports.report":
        role_name = getattr(getattr(user, "role", None), "name", None)
        if role_name != Role.SUPER_ADMIN and instance.created_by_id != user.pk:
            raise ProtectedAttachmentAccessDenied("Protected file access is forbidden.")
    else:
        raise ProtectedAttachmentAccessDenied("Unsupported protected file owner.")
    return instance


def open_authorized_protected_file(user, instance, field_name):
    authorize_protected_file_download(user, instance)
    field_file = getattr(instance, field_name, None)
    if not field_file:
        raise ProtectedAttachmentNotFound("Protected file not found.")
    try:
        field_file.open("rb")
    except (FileNotFoundError, OSError) as exc:
        raise ProtectedAttachmentNotFound("Protected file not found.") from exc
    return field_file


def open_authorized_attachment(user, attachment):
    """Authorize and open a protected file without producing a public URL."""
    authorize_attachment_download(user, attachment)
    try:
        attachment.file.open("rb")
    except (FileNotFoundError, OSError) as exc:
        raise ProtectedAttachmentNotFound("Attachment file not found.") from exc
    return attachment.file
