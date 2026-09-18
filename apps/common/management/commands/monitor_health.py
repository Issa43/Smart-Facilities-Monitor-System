import json

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from redis import Redis


class Command(BaseCommand):
    help = "Exit non-zero when database, Redis, or Celery queue health breaches thresholds."

    def add_arguments(self, parser):
        parser.add_argument("--max-queue-depth", type=int, default=100)

    def handle(self, *args, **options):
        status = {"database": False, "redis": False, "queue_depth": -1}
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                status["database"] = cursor.fetchone()[0] == 1
            cache.set("monitor-health", "ok", timeout=10)
            status["redis"] = cache.get("monitor-health") == "ok"
            status["queue_depth"] = Redis.from_url(settings.CELERY_BROKER_URL).llen(
                settings.CELERY_TASK_DEFAULT_QUEUE
            )
        except Exception as error:
            status["error"] = type(error).__name__
        self.stdout.write(json.dumps(status, sort_keys=True))
        if (
            not status["database"]
            or not status["redis"]
            or status["queue_depth"] < 0
            or status["queue_depth"] > options["max_queue_depth"]
        ):
            raise CommandError("Operational health threshold breached.")
