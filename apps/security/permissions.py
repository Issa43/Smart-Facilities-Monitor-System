from rest_framework.permissions import BasePermission

from .models import AIIngestionCredential


class IsAIIngestionMachine(BasePermission):
    """Reusable permission for future machine-only ingestion endpoints."""

    message = "Valid machine authentication is required."

    def has_permission(self, request, view):
        credential = getattr(request, "auth", None)
        user = getattr(request, "user", None)
        return bool(
            isinstance(credential, AIIngestionCredential)
            and credential.is_usable
            and user
            and user.pk == credential.principal_id
            and not user.role_id
        )
