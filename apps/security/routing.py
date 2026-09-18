from django.urls import path

from .consumers import SecurityEventConsumer


websocket_urlpatterns = [
    path("ws/security/events/", SecurityEventConsumer.as_asgi()),
]
