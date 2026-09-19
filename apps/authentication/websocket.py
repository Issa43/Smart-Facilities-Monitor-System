from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken, TokenError

from apps.users.models import User


JWT_WEBSOCKET_SUBPROTOCOL = "sflms.jwt"


@database_sync_to_async
def _authenticate_access_token(raw_token):
    try:
        authenticator = JWTAuthentication()
        validated_token = authenticator.get_validated_token(raw_token)
        authenticated_user = authenticator.get_user(validated_token)
        return User.objects.select_related("role").get(pk=authenticated_user.pk)
    except (AuthenticationFailed, InvalidToken, TokenError, User.DoesNotExist):
        return AnonymousUser()


class JWTSubprotocolAuthMiddleware:
    """Authenticate a human access JWT without putting it in the URL."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        scoped = dict(scope)
        subprotocols = list(scoped.get("subprotocols") or [])
        raw_token = None
        if len(subprotocols) == 2 and subprotocols[0] == JWT_WEBSOCKET_SUBPROTOCOL:
            raw_token = subprotocols[1]
        scoped["user"] = (
            await _authenticate_access_token(raw_token)
            if raw_token
            else AnonymousUser()
        )
        scoped["subprotocols"] = (
            [JWT_WEBSOCKET_SUBPROTOCOL] if raw_token else []
        )
        return await self.inner(scoped, receive, send)
