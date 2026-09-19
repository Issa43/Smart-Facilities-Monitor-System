import json
import logging
import threading
import time
from collections import Counter
from datetime import datetime, timezone

from django.conf import settings
from django.db import connection
from django.http import HttpResponse
from django.views.decorators.http import require_GET
from redis import Redis


class JsonFormatter(logging.Formatter):
    """One JSON object per line for container log collectors."""

    def format(self, record):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_started = time.monotonic()
_lock = threading.Lock()
_requests = Counter()
_latency_seconds = Counter()


class OperationalMetricsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.monotonic()
        response = self.get_response(request)
        route = getattr(getattr(request, "resolver_match", None), "route", None) or "unmatched"
        key = (request.method, route, str(response.status_code))
        with _lock:
            _requests[key] += 1
            _latency_seconds[key] += time.monotonic() - started
        return response


def _metric(value, name, labels=None):
    suffix = ""
    if labels:
        escaped = ",".join(f'{key}="{str(item).replace(chr(34), chr(92) + chr(34))}"' for key, item in labels.items())
        suffix = "{" + escaped + "}"
    return f"{name}{suffix} {value}"


@require_GET
def metrics(request):
    lines = [
        "# HELP sflms_uptime_seconds Process uptime.",
        "# TYPE sflms_uptime_seconds gauge",
        _metric(round(time.monotonic() - _started, 3), "sflms_uptime_seconds"),
    ]
    with _lock:
        request_snapshot = dict(_requests)
        latency_snapshot = dict(_latency_seconds)
    for (method, route, status_code), count in sorted(request_snapshot.items()):
        labels = {"method": method, "route": route, "status": status_code}
        lines.append(_metric(count, "sflms_http_requests_total", labels))
        lines.append(_metric(round(latency_snapshot[(method, route, status_code)], 6), "sflms_http_request_duration_seconds_total", labels))

    database_ok = 0
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            database_ok = int(cursor.fetchone()[0] == 1)
    except Exception:
        pass
    lines.append(_metric(database_ok, "sflms_database_up"))

    queue_depth = -1
    try:
        queue_depth = Redis.from_url(settings.CELERY_BROKER_URL).llen(
            settings.CELERY_TASK_DEFAULT_QUEUE
        )
    except Exception:
        pass
    lines.append(_metric(queue_depth, "sflms_celery_queue_depth", {"queue": settings.CELERY_TASK_DEFAULT_QUEUE}))
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; version=0.0.4")
