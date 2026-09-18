from .base import *  # noqa: F401,F403


DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
# Mail stays in memory. The host/port are pinned too, because base.py reads them
# from the environment and the dev containers export EMAIL_HOST=mailpit: the
# locmem backend ignores them, but test settings should never inherit a
# deployment target rather than declare its own.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
EMAIL_HOST = "localhost"
EMAIL_PORT = 25
EMAIL_HOST_USER = ""
EMAIL_HOST_PASSWORD = ""
EMAIL_USE_TLS = False
EMAIL_USE_SSL = False

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "sflms-tests",
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
# Second line of defence. Eager execution alone is a single switch: if it were
# ever turned off, .delay() would publish to whatever broker the environment
# supplies — which is how a test run once reached the development Redis. An
# in-memory transport means a publish that escapes eager mode still cannot
# leave the process. Nothing in development or production reads these.
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = False
CELERY_BROKER_CONNECTION_MAX_RETRIES = 0

# Credentials are never inherited from the environment during tests. A real bot
# token or FCM key present in the shell must not become usable just because a
# suite happens to run there; every external integration is off and unarmed.
SAFETY_TELEGRAM_ENABLED = False
SAFETY_TELEGRAM_BOT_TOKEN = ""
FCM_ENABLED = False
FCM_PROJECT_ID = ""
FCM_CREDENTIALS_PATH = ""
# Provider polling stays behind its kill switch; individual tests opt in via the
# `settings` fixture, which cannot reach the network under the guards below.
SAFETY_ALERTS_ENABLED = False
