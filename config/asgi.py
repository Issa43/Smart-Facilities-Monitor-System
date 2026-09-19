import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

django_asgi_application = get_asgi_application()

from apps.authentication.websocket import JWTSubprotocolAuthMiddleware
from apps.security.routing import websocket_urlpatterns


application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,
        "websocket": AllowedHostsOriginValidator(
            JWTSubprotocolAuthMiddleware(URLRouter(websocket_urlpatterns))
        ),
    }
)
