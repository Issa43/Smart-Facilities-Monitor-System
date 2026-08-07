import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

django_asgi_application = get_asgi_application()

# Phase 2 infrastructure foundation. Phase 7 will replace the empty
# WebSocket URLRouter with notification routes and JWT authentication.
application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,
        "websocket": URLRouter([]),
    }
)
