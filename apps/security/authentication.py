from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .machine_credentials import perform_dummy_secret_check, verify_machine_secret
from .models import AIIngestionCredential


class AIIngestionAuthentication(BaseAuthentication):
    """Authenticate `Authorization: AIKey <key_id>:<secret>` credentials."""

    keyword = "AIKey"
    failure_message = "Invalid machine credentials."

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        scheme = parts[0].decode("ascii", errors="ignore").lower() if parts else ""
        if scheme != self.keyword.lower():
            return None
        if len(parts) != 2:
            raise AuthenticationFailed(self.failure_message)
        try:
            token = parts[1].decode("ascii")
            key_id, secret = token.split(":", 1)
        except (UnicodeDecodeError, ValueError):
            raise AuthenticationFailed(self.failure_message)
        if not key_id or not secret:
            raise AuthenticationFailed(self.failure_message)

        credential = (
            AIIngestionCredential.all_objects.select_related("principal")
            .filter(key_id=key_id)
            .first()
        )
        if credential is None:
            perform_dummy_secret_check(secret)
            raise AuthenticationFailed(self.failure_message)
        if not credential.is_usable or not verify_machine_secret(
            secret, credential.secret_hash
        ):
            raise AuthenticationFailed(self.failure_message)

        now = timezone.now()
        AIIngestionCredential.all_objects.filter(pk=credential.pk).update(
            last_used_at=now
        )
        credential.last_used_at = now
        return credential.principal, credential

    def authenticate_header(self, request):
        return self.keyword


class AIIngestionAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.security.authentication.AIIngestionAuthentication"
    name = "AIKeyAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": (
                "Machine-only credential: AIKey <key_id>:<secret>. "
                "The secret is returned only when a credential is created or rotated."
            ),
        }
