from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.authentication.websocket import JWT_WEBSOCKET_SUBPROTOCOL
from apps.users.models import Role, User

from .realtime import security_user_group


@database_sync_to_async
def _can_receive_security_events(user_id):
    user = User.objects.select_related("role").filter(
        pk=user_id,
        status=User.STATUS_ACTIVE,
        role__isnull=False,
    ).first()
    if user is None:
        return False
    if user.role.name == Role.SUPER_ADMIN:
        return True
    return bool(
        user.role.name == Role.SECURITY_OFFICER
        and user.role.permissions.filter(permission_name="alert.view").exists()
    )


class SecurityEventConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not getattr(user, "is_authenticated", False):
            await self.close(code=4401)
            return
        if not await _can_receive_security_events(user.pk):
            await self.close(code=4403)
            return

        self.security_group = security_user_group(user.pk)
        await self.channel_layer.group_add(self.security_group, self.channel_name)
        await self.accept(subprotocol=JWT_WEBSOCKET_SUBPROTOCOL)
        await self.send_json(
            {
                "type": "security.connection.ready",
                "version": 1,
            }
        )

    async def disconnect(self, close_code):
        group = getattr(self, "security_group", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        await self.send_json(
            {
                "type": "security.error",
                "version": 1,
                "error": {
                    "code": "read_only",
                    "message": "This WebSocket is server-to-client only.",
                },
            }
        )

    async def security_message(self, event):
        await self.send_json(event["payload"])
