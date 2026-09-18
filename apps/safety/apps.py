from django.apps import AppConfig


class SafetyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.safety"
    verbose_name = "External Safety Alerts"

    def ready(self):
        # Celery autodiscovery imports only ``tasks``; the Telegram delivery
        # task lives apart from provider polling and is registered here.
        from . import telegram_tasks  # noqa: F401
