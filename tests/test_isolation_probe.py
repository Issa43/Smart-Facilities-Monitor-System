"""The probe half of the §9 incident regression.

Run twice: once by the normal suite, and once as a subprocess with
``DJANGO_SETTINGS_MODULE=config.settings.development`` by
``tests/test_test_isolation.py``. Both runs must reach the same conclusion —
the runtime is isolated — which is what proves the accidental-development
scenario can no longer reach real infrastructure.

Kept free of database access so the subprocess run stays fast.
"""

import socket

from django.conf import settings

from config.celery import app as celery_app, infrastructure_health


def test_runtime_uses_the_test_settings_module():
    assert settings.SETTINGS_MODULE == "config.settings.test"


def test_celery_cannot_reach_a_real_broker():
    assert settings.CELERY_TASK_ALWAYS_EAGER is True
    assert settings.CELERY_BROKER_URL.startswith("memory://")
    assert "redis" not in settings.CELERY_BROKER_URL
    # Celery resolves these from the environment ahead of Django settings, so
    # each one is asserted on the Celery side, not just the Django side.
    for url in (
        celery_app.conf.broker_url,
        celery_app.conf.broker_read_url,
        celery_app.conf.broker_write_url,
    ):
        assert str(url).startswith("memory://"), url
    assert "redis" not in str(celery_app.conf.result_backend)


def test_delay_executes_in_process_and_publishes_nothing():
    """The exact call that leaked in the incident: .delay() on a real task."""

    result = infrastructure_health.delay()
    # Eager execution returns a finished result without touching a broker.
    assert result.get() == {"status": "ok", "service": "celery"}


def test_external_connections_are_refused():
    for address in [
        ("api.telegram.org", 443),
        ("earthquake.usgs.gov", 443),
        ("www.gdacs.org", 443),
        ("fcm.googleapis.com", 443),
        ("redis", 6379),
        ("postgres", 5432),
    ]:
        try:
            socket.create_connection(address, timeout=1)
        except Exception as exc:  # noqa: BLE001 - the type is the assertion
            assert type(exc).__name__ == "ExternalNetworkBlocked", (address, exc)
        else:
            raise AssertionError(f"Connection to {address} was not blocked.")


def test_no_external_credentials_are_armed():
    assert settings.SAFETY_TELEGRAM_ENABLED is False
    assert settings.SAFETY_TELEGRAM_BOT_TOKEN == ""
    assert settings.FCM_ENABLED is False
    assert settings.FCM_CREDENTIALS_PATH == ""
    assert settings.SAFETY_ALERTS_ENABLED is False
