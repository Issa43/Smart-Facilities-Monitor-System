from decouple import config
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

DEBUG = False

if SECRET_KEY == "insecure-dev-key-change-me" or SECRET_KEY.startswith("change-me"):
    raise ImproperlyConfigured("A strong SECRET_KEY must be configured in production.")

SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=False, cast=bool)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0

if config("USE_X_FORWARDED_PROTO", default=True, cast=bool):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# NOTE: Docker Compose is the official deployment environment (ADR-0004,
# docs/docker.md). This module applies regardless of host — Docker or
# future cloud — since production hardening settings don't change based
# on container orchestration.
