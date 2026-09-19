"""
Celery application instance for SFLMS.

Present from Phase 1 so the project structure matches the approved
architecture (`config/` containing settings, urls, wsgi, asgi, celery).
Phase 2 activates the worker/beat infrastructure and includes one
side-effect-free health task. Phase 3 adds the report-generation task;
other domain tasks remain deferred.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("sflms")

# Reads CELERY_* settings from Django settings (config/settings/base.py),
# already configured with CELERY_BROKER_URL / CELERY_RESULT_BACKEND (Redis).
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discovers registered app tasks, currently including report generation.
app.autodiscover_tasks()


@app.task(name="sflms.infrastructure_health")
def infrastructure_health():
    """Side-effect-free task used to verify that workers can execute jobs."""

    return {"status": "ok", "service": "celery"}
