from pathlib import Path
import json
import logging
from unittest.mock import Mock, patch

import pytest
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from config.celery import app as celery_app
from config.celery import infrastructure_health
from apps.audit.middleware import ApiMutationAuditMiddleware
from apps.audit.models import AuditLog
from apps.common.observability import JsonFormatter


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


@pytest.mark.django_db
def test_metrics_endpoint_exposes_database_and_queue_health(client):
    redis = Mock()
    redis.llen.return_value = 3
    with patch("apps.common.observability.Redis.from_url", return_value=redis):
        response = client.get(reverse("metrics"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "sflms_database_up 1" in body
    assert 'sflms_celery_queue_depth{queue="default"} 3' in body


def test_json_log_formatter_emits_structured_record():
    record = logging.LogRecord("sflms.test", logging.ERROR, __file__, 1, "failure", (), None)
    payload = json.loads(JsonFormatter().format(record))
    assert payload == {
        "timestamp": payload["timestamp"],
        "level": "ERROR",
        "logger": "sflms.test",
        "message": "failure",
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "expected_action"),
    (("post", "api.post"), ("patch", "api.patch")),
)
def test_mutation_audit_preserves_successful_envelopes_and_long_endpoint_reference(
    super_admin_user,
    method,
    expected_action,
):
    request = getattr(RequestFactory(), method)(
        f"/api/v1/security/incidents/{'a' * 180}/notes/"
    )
    request.user = super_admin_user
    middleware = ApiMutationAuditMiddleware(lambda _request: HttpResponse(status=201))

    with (
        patch("apps.audit.middleware.setting_enabled", return_value=True),
        patch(
            "apps.audit.middleware.transaction.on_commit",
            side_effect=lambda callback: callback(),
        ),
    ):
        response = middleware(request)

    assert response.status_code == 201
    entry = AuditLog.objects.get()
    assert entry.action == expected_action
    assert entry.entity_type == "api_endpoint"
    assert len(entry.entity_id) == 100
    assert entry.entity_ref == request.path[:255]


@pytest.mark.django_db
def test_my_audit_endpoint_remains_complete_and_actor_scoped(
    api_client,
    super_admin_user,
    construction_manager_user,
):
    AuditLog.objects.create(
        actor=super_admin_user,
        action="asset.created",
        entity_type="assets.asset",
        entity_id="asset-1",
        entity_ref="Main Pump (PUMP-1)",
    )
    AuditLog.objects.create(
        actor=super_admin_user,
        action="api.post",
        entity_type="api_endpoint",
        entity_id="/api/v1/assets/",
        entity_ref="/api/v1/assets/",
    )
    AuditLog.objects.create(
        actor=construction_manager_user,
        action="api.patch",
        entity_type="api_endpoint",
        entity_id="/api/v1/users/me/",
        entity_ref="/api/v1/users/me/",
    )

    api_client.force_authenticate(super_admin_user)
    response = api_client.get("/api/v1/audit-logs/mine/")

    assert response.status_code == 200
    entries = response.data["results"]
    assert {entry["action"] for entry in entries} == {"asset.created", "api.post"}
    assert {entry["actor_id"] for entry in entries} == {str(super_admin_user.pk)}


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


# ---------------------------------------------------------------------------
# Local mail capture (Mailpit)
#
# Development delivers password-reset mail to a local Mailpit inbox instead of
# printing it to the container log. These tests read the compose files and the
# settings module; none of them opens a socket, so the suite stays offline.
# ---------------------------------------------------------------------------

COMPOSE_ROOT = Path(__file__).resolve().parent.parent


def _compose(name):
    return (COMPOSE_ROOT / name).read_text(encoding="utf-8")


def test_pytest_email_backend_stays_in_memory():
    """Tests must never reach Mailpit, SMTP, or any socket."""

    if settings.SETTINGS_MODULE != "config.settings.test":
        pytest.skip("only meaningful under the test settings module")
    assert settings.EMAIL_BACKEND == "django.core.mail.backends.locmem.EmailBackend"
    assert "smtp" not in settings.EMAIL_BACKEND
    assert settings.EMAIL_HOST != "mailpit"


def test_development_overlay_sends_mail_to_mailpit():
    overlay = _compose("docker-compose.override.yml")
    assert "mailpit:" in overlay
    assert "axllent/mailpit" in overlay
    assert "EMAIL_BACKEND: django.core.mail.backends.smtp.EmailBackend" in overlay
    assert "EMAIL_HOST: mailpit" in overlay
    assert 'EMAIL_PORT: "1025"' in overlay
    assert 'EMAIL_USE_TLS: "False"' in overlay
    assert 'EMAIL_USE_SSL: "False"' in overlay
    # A local sink needs no credentials, so none may be introduced here.
    assert "EMAIL_HOST_PASSWORD" not in overlay


def test_mailpit_is_local_only_and_absent_from_production():
    """Production must never be wired to the local mail sink."""

    for name in ("docker-compose.yml", "docker-compose.production.yml"):
        compose = _compose(name)
        assert "mailpit" not in compose.lower(), name
        assert "EMAIL_HOST: mailpit" not in compose, name


def test_production_email_settings_remain_environment_driven():
    """The SMTP host/credentials stay configurable, never hard-coded."""

    source = (COMPOSE_ROOT / "config" / "settings" / "base.py").read_text(encoding="utf-8")
    for name in ("EMAIL_BACKEND", "EMAIL_HOST", "EMAIL_PORT", "EMAIL_USE_TLS", "EMAIL_USE_SSL"):
        # Each is read through decouple's `config(...)`, so a deployment can
        # point them anywhere without a code change.
        assert f'"{name}"' in source, name
        assert f"{name} = config(" in source, name
    # Mailpit may be mentioned in a comment, but never assigned as a value.
    assert '"mailpit"' not in source.lower()
    assert "'mailpit'" not in source.lower()
    production = (COMPOSE_ROOT / "config" / "settings" / "production.py").read_text(encoding="utf-8")
    assert "mailpit" not in production.lower()


def test_password_reset_delivery_contract_is_unchanged():
    """The reset link shape and token lifetime are not affected by Mailpit."""

    assert "{uid}" in settings.FRONTEND_PASSWORD_RESET_URL
    assert "{token}" in settings.FRONTEND_PASSWORD_RESET_URL
    assert "/reset-password?" in settings.FRONTEND_PASSWORD_RESET_URL
    assert settings.PASSWORD_RESET_TIMEOUT == 1800
