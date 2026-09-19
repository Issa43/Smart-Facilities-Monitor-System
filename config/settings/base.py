"""
Base settings shared by all environments.
Smart Facility Lifecycle Management System (SFLMS) - Backend
"""
from datetime import timedelta
from pathlib import Path

import dj_database_url
from decouple import Csv, config

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = config("SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1,backend", cast=Csv())

# ---------------------------------------------------------------------------
# Applications
#
# App structure follows the approved architecture document exactly
# (SFLMS_Backend_Architecture_v2.md, section 2 + addendum in section 9).
# Only apps implemented so far are registered. Apps belonging to later
# phases exist as empty placeholders on disk but are intentionally NOT
# added here until their phase is implemented, to keep `migrate` clean.
# ---------------------------------------------------------------------------
ASGI_APPS = [
    # Must precede django.contrib.staticfiles so Daphne owns `runserver`.
    "daphne",
]

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "django_filters",
    "corsheaders",
]

# Implemented application registrations
LOCAL_APPS = [
    "apps.common",
    "apps.users",
    "apps.authentication",
    # Phase 3 foundation
    "apps.attachments.apps.AttachmentsConfig",
    "apps.projects.apps.ProjectsConfig",
    "apps.facilities.apps.FacilitiesConfig",
    "apps.construction.apps.ConstructionConfig",
    "apps.materials.apps.MaterialsConfig",
    "apps.assets.apps.AssetsConfig",
    "apps.maintenance.apps.MaintenanceConfig",
    "apps.security.apps.SecurityConfig",
    "apps.reports.apps.ReportsConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.audit.apps.AuditConfig",
    "apps.safety.apps.SafetyConfig",
]

# --- Apps planned by the approved architecture, added incrementally per phase ---
# "apps.ai_engine"       # Phase 6
# Notifications and audit are registered because they are authoritative
# cross-cutting domains used by every production workflow.

INSTALLED_APPS = ASGI_APPS + DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = "users.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.common.observability.OperationalMetricsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.audit.middleware.ApiMutationAuditMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        # Kept only because Django admin requires the template engine.
        # No app templates are used - this is a REST API only backend.
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database - PostgreSQL
# ---------------------------------------------------------------------------
DATABASE_URL = config("DATABASE_URL", default="")
DB_CONN_MAX_AGE = config("DB_CONN_MAX_AGE", default=60, cast=int)

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=DB_CONN_MAX_AGE,
            ssl_require=config("DB_SSL_REQUIRE", default=False, cast=bool),
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("DB_NAME", default="sflms_db"),
            "USER": config("DB_USER", default="sflms_user"),
            "PASSWORD": config("DB_PASSWORD", default=""),
            "HOST": config("DB_HOST", default="postgres"),
            "PORT": config("DB_PORT", default="5432"),
            "CONN_MAX_AGE": DB_CONN_MAX_AGE,
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media files (local filesystem strategy - see architecture §7)
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
PROTECTED_MEDIA_ROOT = BASE_DIR / "protected_media"
DATA_UPLOAD_MAX_MEMORY_SIZE = config(
    "DATA_UPLOAD_MAX_MEMORY_SIZE", default=30 * 1024 * 1024, cast=int
)
FILE_UPLOAD_MAX_MEMORY_SIZE = config(
    "FILE_UPLOAD_MAX_MEMORY_SIZE", default=5 * 1024 * 1024, cast=int
)

# Abstracted default storage backend - swappable for cloud storage later
# without touching models or APIs (architecture §7).
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "protected": {
        "BACKEND": "apps.attachments.storage.ProtectedFileSystemStorage",
        "OPTIONS": {
            "location": PROTECTED_MEDIA_ROOT,
        },
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

WHITENOISE_AUTOREFRESH = DEBUG

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardResultsPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": config("API_ANON_RATE", default="60/minute"),
        "user": config("API_USER_RATE", default="600/minute"),
        "ai_ingestion": config("AI_INGESTION_RATE", default="1200/minute"),
        "password_reset": config("PASSWORD_RESET_RATE", default="5/minute"),
    },
    "EXCEPTION_HANDLER": "apps.common.exceptions.custom_exception_handler",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

# ---------------------------------------------------------------------------
# JWT (Simple JWT) - Access + Refresh tokens, architecture §9.7
# ---------------------------------------------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=config("ACCESS_TOKEN_LIFETIME_MINUTES", default=30, cast=int)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=config("REFRESH_TOKEN_LIFETIME_DAYS", default=7, cast=int)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "CHECK_REVOKE_TOKEN": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ---------------------------------------------------------------------------
# drf-spectacular (Swagger / OpenAPI)
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "SFLMS API",
    "DESCRIPTION": "Smart Facility Lifecycle Management System - Backend REST API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": True},
    # Enum component names are assigned globally by field name. These entries
    # keep the pre-existing Fault severity and Project status component names
    # stable after the Safety API added other "severity"/"status" choice sets,
    # and give the Safety alert choice sets explicit names.
    "ENUM_NAME_OVERRIDES": {
        "SeverityEnum": "apps.maintenance.models.Fault.Severity",
        "ProjectReadStatusEnum": "apps.projects.models.Project.Status",
        "SafetyAlertSeverityEnum": "api.v1.safety.serializers.SAFETY_SEVERITY_CHOICES",
        "SafetyAlertStatusEnum": "apps.safety.models.ProjectSafetyAlert.Status",
        "SafetyActionEnum": "apps.safety.models.ProjectSafetyAlert.Action",
        "SafetyRecommendedActionEnum": "api.v1.safety.serializers.RECOMMENDED_ACTION_CHOICES",
    },
}

# ---------------------------------------------------------------------------
# CORS - frontend is a separate HTML/CSS/JS client
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="", cast=Csv())
CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ["Content-Disposition", "Content-Length"]
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

# Password reset delivery. Production must configure an SMTP backend and a
# frontend URL containing both ``{uid}`` and ``{token}`` placeholders.
EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="no-reply@sflms.local")
EMAIL_HOST = config("EMAIL_HOST", default="localhost")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
# Django forbids enabling both; local Mailpit uses plaintext SMTP with neither.
EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=False, cast=bool)
FRONTEND_PASSWORD_RESET_URL = config(
    "FRONTEND_PASSWORD_RESET_URL",
    default="http://localhost:5173/reset-password?uid={uid}&token={token}",
)
PASSWORD_RESET_TIMEOUT = config("PASSWORD_RESET_TIMEOUT_SECONDS", default=1800, cast=int)

# ---------------------------------------------------------------------------
# Redis cache, Celery, and Channels infrastructure
# ---------------------------------------------------------------------------
REDIS_URL = config("REDIS_URL", default="redis://redis:6379/0")
CACHE_URL = config("CACHE_URL", default="redis://redis:6379/1")
CHANNEL_REDIS_URL = config("CHANNEL_REDIS_URL", default="redis://redis:6379/2")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": CACHE_URL,
        "TIMEOUT": config("CACHE_DEFAULT_TIMEOUT", default=300, cast=int),
    }
}

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "notify-project-completion-reminders-daily": {
        "task": "notifications.notify_project_completion_reminders",
        "schedule": 24 * 60 * 60,
    },
    "notify-overdue-work-orders-daily": {
        "task": "notifications.notify_overdue_work_orders",
        "schedule": 24 * 60 * 60,
    },
    "notify-critical-security-alerts": {
        "task": "notifications.notify_critical_security_alerts",
        "schedule": 60.0,
    },
    "recover-queued-push-deliveries": {
        "task": "notifications.recover_queued_push_deliveries",
        "schedule": 60.0,
    },
}

# Firebase Admin is initialized lazily by Celery. Missing credentials never
# prevent Django or workers from starting, and never count as a successful send.
FCM_ENABLED = config("FCM_ENABLED", default=False, cast=bool)
FCM_PROJECT_ID = config("FCM_PROJECT_ID", default="")
FCM_CREDENTIALS_PATH = config("FCM_CREDENTIALS_PATH", default="")

# External safety alerting kill switch. Alert creation also requires the
# ``safety.externalAlerts`` SystemSetting; both default to disabled.
SAFETY_ALERTS_ENABLED = config("SAFETY_ALERTS_ENABLED", default=False, cast=bool)


def _bounded_int_setting(name, default, minimum, maximum):
    return max(minimum, min(maximum, config(name, default=default, cast=int)))


# External hazard provider polling. Polls exit before any network call unless
# both Safety kill switches are on. Endpoint URLs are still checked against a
# fixed host allowlist in apps/safety/providers before every request.
SAFETY_USGS_ENABLED = config("SAFETY_USGS_ENABLED", default=True, cast=bool)
SAFETY_USGS_FEED_URL = config(
    "SAFETY_USGS_FEED_URL",
    default="https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson",
)
SAFETY_USGS_POLL_SECONDS = _bounded_int_setting("SAFETY_USGS_POLL_SECONDS", 300, 60, 3600)
SAFETY_GDACS_ENABLED = config("SAFETY_GDACS_ENABLED", default=True, cast=bool)
SAFETY_GDACS_EVENTS_URL = config(
    "SAFETY_GDACS_EVENTS_URL",
    default="https://www.gdacs.org/gdacsapi/api/events/geteventlist/EVENTS4APP",
)
SAFETY_GDACS_POLL_SECONDS = _bounded_int_setting("SAFETY_GDACS_POLL_SECONDS", 900, 60, 3600)
SAFETY_PROVIDER_TIMEOUT_SECONDS = _bounded_int_setting("SAFETY_PROVIDER_TIMEOUT_SECONDS", 10, 1, 30)
SAFETY_PROVIDER_MAX_BYTES = _bounded_int_setting(
    "SAFETY_PROVIDER_MAX_BYTES", 5 * 1024 * 1024, 64 * 1024, 20 * 1024 * 1024
)
SAFETY_PROVIDER_MAX_RETRIES = _bounded_int_setting("SAFETY_PROVIDER_MAX_RETRIES", 2, 0, 3)

# Official Syrian MHEWS weather warnings (CAP 1.2). Disabled by default and
# additionally gated by both Safety kill switches, so nothing is fetched until
# an operator turns it on. The feed URL is fixed in code, not read from the
# environment, so a token-free public endpoint cannot be redirected elsewhere;
# the host allowlist in apps/safety/providers/mhews.py is checked regardless.
SAFETY_WEATHER_ENABLED = config("SAFETY_WEATHER_ENABLED", default=False, cast=bool)
SAFETY_MHEWS_FEED_URL = "https://climweb.med.gov.sy/api/cap/rss.xml"
SAFETY_MHEWS_POLL_SECONDS = _bounded_int_setting("SAFETY_MHEWS_POLL_SECONDS", 900, 300, 3600)

# Outbound-only Telegram delivery of human safety decisions. Disabled by
# default: when off, nothing is queued, no row is written, and no network call
# is made. The bot token is read from the environment and never logged, stored
# in the database, or returned by any API. There is no inbound webhook.
SAFETY_TELEGRAM_ENABLED = config("SAFETY_TELEGRAM_ENABLED", default=False, cast=bool)
SAFETY_TELEGRAM_BOT_TOKEN = config("SAFETY_TELEGRAM_BOT_TOKEN", default="")
SAFETY_TELEGRAM_API_BASE_URL = "https://api.telegram.org"
SAFETY_TELEGRAM_TIMEOUT_SECONDS = _bounded_int_setting("SAFETY_TELEGRAM_TIMEOUT_SECONDS", 10, 1, 30)
SAFETY_TELEGRAM_MAX_RETRIES = _bounded_int_setting("SAFETY_TELEGRAM_MAX_RETRIES", 3, 0, 5)
SAFETY_TELEGRAM_MAX_MESSAGE_CHARS = _bounded_int_setting(
    "SAFETY_TELEGRAM_MAX_MESSAGE_CHARS", 3500, 500, 4096
)

CELERY_BEAT_SCHEDULE.update(
    {
        "safety-poll-usgs-earthquakes": {
            "task": "safety.poll_usgs_earthquakes",
            "schedule": float(SAFETY_USGS_POLL_SECONDS),
            "options": {"expires": SAFETY_USGS_POLL_SECONDS},
        },
        "safety-poll-gdacs-events": {
            "task": "safety.poll_gdacs_events",
            "schedule": float(SAFETY_GDACS_POLL_SECONDS),
            "options": {"expires": SAFETY_GDACS_POLL_SECONDS},
        },
        "safety-poll-mhews-warnings": {
            "task": "safety.poll_mhews_warnings",
            "schedule": float(SAFETY_MHEWS_POLL_SECONDS),
            "options": {"expires": SAFETY_MHEWS_POLL_SECONDS},
        },
    }
)

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [CHANNEL_REDIS_URL]},
    }
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = config("LOG_LEVEL", default="INFO").upper()
DJANGO_LOG_LEVEL = config("DJANGO_LOG_LEVEL", default=LOG_LEVEL).upper()
LOG_FORMAT = config("LOG_FORMAT", default="json").lower()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
        "json": {"()": "apps.common.observability.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if LOG_FORMAT == "json" else "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": DJANGO_LOG_LEVEL,
            "propagate": False,
        },
    },
}
