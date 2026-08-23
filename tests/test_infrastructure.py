from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse

from config.celery import app as celery_app
from config.celery import infrastructure_health


def test_environment_backed_infrastructure_settings():
    if settings.SETTINGS_MODULE == "config.settings.test":
        assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
        assert settings.CACHES["default"]["BACKEND"].endswith("LocMemCache")
        assert settings.CHANNEL_LAYERS["default"]["BACKEND"].endswith("InMemoryChannelLayer")
        assert settings.CELERY_TASK_ALWAYS_EAGER is True
        return
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
    assert settings.DATABASES["default"]["HOST"] == "postgres"
    assert settings.CACHES["default"]["BACKEND"].endswith("RedisCache")
    assert settings.CACHES["default"]["LOCATION"].startswith("redis://redis:")
    assert settings.CHANNEL_LAYERS["default"]["BACKEND"].endswith("RedisChannelLayer")
    assert settings.CELERY_BROKER_URL.startswith("redis://redis:")


def test_liveness_endpoint_has_no_dependency_requirement(client):
    response = client.get(reverse("health"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "backend"}


@pytest.mark.django_db
def test_database_health_endpoint(client):
    response = client.get(reverse("health-db"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "postgres"}


def test_database_health_endpoint_reports_unavailable(client):
    unavailable_connection = Mock()
    unavailable_connection.cursor.side_effect = RuntimeError("offline")
    with patch("apps.common.health.connection", unavailable_connection):
        response = client.get(reverse("health-db"))
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "service": "postgres"}


def test_redis_health_endpoint(client):
    response = client.get(reverse("health-redis"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "redis"}


def test_redis_health_endpoint_reports_unavailable(client):
    unavailable_cache = Mock()
    unavailable_cache.set.side_effect = RuntimeError("offline")
    with patch("apps.common.health.caches", {"default": unavailable_cache}):
        response = client.get(reverse("health-redis"))
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "service": "redis"}


def test_redis_cache_round_trip():
    cache.set("infrastructure-test", "ok", timeout=5)
    assert cache.get("infrastructure-test") == "ok"
    cache.delete("infrastructure-test")


def test_celery_configuration_and_health_task():
    assert celery_app.conf.broker_url == settings.CELERY_BROKER_URL
    assert celery_app.conf.result_backend == settings.CELERY_RESULT_BACKEND
    assert infrastructure_health.run() == {"status": "ok", "service": "celery"}


def test_compose_declares_required_infrastructure():
    repository_root = Path(__file__).resolve().parent.parent
    compose = (repository_root / "docker-compose.yml").read_text(encoding="utf-8")

    for service in ("backend", "postgres", "redis", "celery_worker", "celery_beat"):
        assert f"  {service}:" in compose

    for volume in (
        "postgres_data",
        "redis_data",
        "static_data",
        "media_data",
        "celery_beat_data",
    ):
        assert f"  {volume}:" in compose

    assert "condition: service_healthy" in compose
    assert "restart: unless-stopped" in compose
    assert "sflms_internal" in compose


def test_development_override_exposes_only_development_ports():
    repository_root = Path(__file__).resolve().parent.parent
    override = (repository_root / "docker-compose.override.yml").read_text(encoding="utf-8")
    assert "${BACKEND_PORT:-8000}:8000" in override
    assert "${POSTGRES_PORT_FORWARD:-5432}:5432" in override
    assert "${REDIS_PORT_FORWARD:-6379}:6379" in override
