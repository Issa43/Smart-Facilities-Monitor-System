import logging
import uuid

from django.core.cache import caches
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@require_GET
def health(request):
    """Process-level liveness check with no external dependencies."""

    return JsonResponse({"status": "ok", "service": "backend"})


@require_GET
def database_health(request):
    """Readiness check for the configured PostgreSQL connection."""

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # noqa: BLE001 - readiness must translate all backend failures
        logger.exception("Database health check failed")
        return JsonResponse({"status": "unavailable", "service": "postgres"}, status=503)

    return JsonResponse({"status": "ok", "service": "postgres"})


@require_GET
def redis_health(request):
    """Readiness check for the Redis-backed default cache."""

    cache = caches["default"]
    key = f"health:{uuid.uuid4()}"
    try:
        cache.set(key, "ok", timeout=5)
        healthy = cache.get(key) == "ok"
        cache.delete(key)
    except Exception:  # noqa: BLE001 - readiness must translate all backend failures
        logger.exception("Redis health check failed")
        healthy = False

    status_code = 200 if healthy else 503
    status_value = "ok" if healthy else "unavailable"
    return JsonResponse({"status": status_value, "service": "redis"}, status=status_code)
