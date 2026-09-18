"""Offline tests for outbound Telegram delivery of safety decisions.

No test performs a real Telegram send. An autouse guard fails any test that
reaches the network, so a regression that bypasses the client is a test
failure rather than an outbound request.
"""

import json
import logging
import urllib.error
import urllib.request

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.projects.models import Project
from apps.safety import telegram
from apps.safety.models import (
    ProjectSafetyAlert,
    SafetyTelegramDelivery,
    SafetyTelegramRecipient,
)
from apps.safety.services import (
    acknowledge_alert,
    close_alert,
    decide_alert_action,
    dismiss_alert,
    ingest_hazard_events,
)
from apps.safety.telegram_tasks import deliver_safety_telegram_message
from apps.safety.telegram_delivery import (
    build_decision_message,
    decision_event_key,
)
from apps.safety.tests.helpers import (
    NOW,
    assign_construction_manager,
    assign_operations_manager,
    enable_alerts,
    make_facility,
    make_project,
    make_user,
    quake,
)
from apps.users.models import Role


pytestmark = pytest.mark.django_db

FAKE_TOKEN = "000000:TEST-BOT-TOKEN-NOT-REAL"


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """Fail loudly if anything in these tests opens a real connection."""

    def explode(*args, **kwargs):
        raise AssertionError("A test attempted a real outbound request.")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", explode)


class FakeResponse:
    def __init__(self, status=200, payload=None, headers=None):
        self.status = status
        self._body = json.dumps(payload if payload is not None else {}).encode("utf-8")
        self.headers = headers or {}

    def read(self, size=None):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeOpener:
    """Records requests instead of sending them."""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.response


def install_opener(monkeypatch, *, response=None, error=None):
    opener = FakeOpener(response=response, error=error)
    monkeypatch.setattr(urllib.request, "build_opener", lambda *a, **k: opener)
    return opener


def http_error(code, payload=None, headers=None):
    error = urllib.error.HTTPError(
        # The URL carries the bot token; the client must never surface it.
        f"https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage",
        code,
        "error",
        headers or {},
        None,
    )
    body = json.dumps(payload if payload is not None else {}).encode("utf-8")
    error.read = lambda size=None: body
    error.headers = headers or {}
    return error


@pytest.fixture
def telegram_on(settings):
    settings.SAFETY_TELEGRAM_ENABLED = True
    settings.SAFETY_TELEGRAM_BOT_TOKEN = FAKE_TOKEN
    settings.SAFETY_TELEGRAM_MAX_RETRIES = 3
    return settings


@pytest.fixture
def world(settings, super_admin_user):
    enable_alerts(settings)
    cm = make_user(Role.CONSTRUCTION_MANAGER, "cm")
    om = make_user(Role.OPERATIONS_MANAGER, "om")
    facility = make_facility(super_admin_user)
    construction = make_project(super_admin_user, name="Construction site")
    operational = make_project(
        super_admin_user,
        name="Operational site",
        status=Project.Status.OPERATIONAL,
        facility=facility,
    )
    assign_construction_manager(construction, cm, super_admin_user)
    assign_operations_manager(facility, om, super_admin_user)
    ingest_hazard_events([quake(magnitude="6.0")], now=NOW)
    return {
        "admin": super_admin_user,
        "cm": cm,
        "om": om,
        "cm_chat": SafetyTelegramRecipient.objects.create(user=cm, chat_id="123456789"),
        "alert": ProjectSafetyAlert.objects.get(project=construction),
        "operational_alert": ProjectSafetyAlert.objects.get(project=operational),
    }


def acknowledged(world):
    alert = world["alert"]
    acknowledge_alert(alert_id=alert.pk, actor=world["cm"])
    return ProjectSafetyAlert.objects.get(pk=alert.pk)


def decide(world, callbacks, *, decision="monitor", notes=""):
    """Record a final decision, as the General Manager.

    Recording a decision is what reaches people, so it carries General Manager
    authority; the Construction Manager's route to the same outcome is a
    proposal for approval (see ``api/v1/safety/tests/test_proposal_api.py``).
    """

    alert = world["alert"]
    with callbacks(execute=True):
        decide_alert_action(
            alert_id=alert.pk,
            actor=world["admin"],
            decision=decision,
            notes=notes,
        )
    return ProjectSafetyAlert.objects.get(pk=alert.pk)


# --------------------------------------------------------------------------
# Destination model
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "chat_id",
    ["", "abc", "1234", "@channelname", "+201234567890", "12 34567", "1" * 21],
)
def test_chat_id_must_be_a_numeric_telegram_id(world, chat_id):
    recipient = SafetyTelegramRecipient(user=world["om"], chat_id=chat_id)
    with pytest.raises(ValidationError) as exc:
        recipient.full_clean()
    assert "chat_id" in exc.value.message_dict


@pytest.mark.parametrize("chat_id", ["987654321", "-1001234567890"])
def test_chat_id_accepts_user_and_group_identifiers(world, chat_id):
    recipient = SafetyTelegramRecipient(user=world["om"], chat_id=chat_id)
    recipient.full_clean()


def test_phone_number_cannot_be_used_as_a_chat_id(world):
    om = world["om"]
    om.phone = "0123456789"
    om.save(update_fields=["phone"])
    recipient = SafetyTelegramRecipient(user=om, chat_id="0123456789")
    with pytest.raises(ValidationError) as exc:
        recipient.full_clean()
    assert "phone number" in str(exc.value.message_dict["chat_id"])


def test_database_rejects_a_malformed_chat_id(world):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            SafetyTelegramRecipient.objects.create(user=world["om"], chat_id="not-a-chat")


def test_one_destination_per_user_and_per_chat_id(world):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            SafetyTelegramRecipient.objects.create(user=world["cm"], chat_id="999888777")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            SafetyTelegramRecipient.objects.create(user=world["om"], chat_id="123456789")


# --------------------------------------------------------------------------
# Trigger: only a recorded human decision
# --------------------------------------------------------------------------


def test_decision_queues_one_delivery_per_configured_destination(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    sent = []
    monkeypatch.setattr(
        telegram,
        "send_message",
        lambda **kwargs: sent.append(kwargs) or "4242",
    )
    acknowledged(world)
    alert = decide(world, django_capture_on_commit_callbacks)

    deliveries = list(SafetyTelegramDelivery.objects.all())
    assert len(deliveries) == 1
    delivery = deliveries[0]
    assert delivery.recipient_id == world["cm_chat"].pk
    assert delivery.status == SafetyTelegramDelivery.Status.SENT
    assert delivery.event_key == decision_event_key(alert)
    assert delivery.provider_message_id == "4242"
    assert delivery.attempt_count == 1
    assert delivery.failure_code == ""
    assert [call["chat_id"] for call in sent] == ["123456789"]


@pytest.mark.parametrize("stage", ["created", "acknowledged", "dismissed", "closed"])
def test_no_other_transition_ever_sends(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch, stage
):
    monkeypatch.setattr(telegram, "send_message", lambda **kwargs: "nope")
    alert = world["alert"]
    with django_capture_on_commit_callbacks(execute=True):
        if stage == "created":
            pass
        elif stage == "acknowledged":
            acknowledge_alert(alert_id=alert.pk, actor=world["cm"])
        elif stage == "dismissed":
            dismiss_alert(alert_id=alert.pk, actor=world["cm"], reason="Out of scope.")
        elif stage == "closed":
            acknowledge_alert(alert_id=alert.pk, actor=world["cm"])
            decide_alert_action(alert_id=alert.pk, actor=world["admin"], decision="monitor")
            SafetyTelegramDelivery.all_objects.all().delete()
            close_alert(alert_id=alert.pk, actor=world["cm"], notes="Done.")
    remaining = SafetyTelegramDelivery.all_objects.count()
    assert remaining == 0


def test_ingestion_and_escalation_never_create_deliveries(
    world, telegram_on, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        ingest_hazard_events([quake(event_id="us-synthetic-1", magnitude="7.4")], now=NOW)
    assert SafetyTelegramDelivery.all_objects.count() == 0


def test_repeating_an_identical_decision_does_not_send_again(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    calls = []
    monkeypatch.setattr(telegram, "send_message", lambda **kwargs: calls.append(1) or "1")
    acknowledged(world)
    decide(world, django_capture_on_commit_callbacks)
    decide(world, django_capture_on_commit_callbacks)
    assert len(calls) == 1
    assert SafetyTelegramDelivery.objects.count() == 1


def test_a_changed_decision_is_a_new_event(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    calls = []
    monkeypatch.setattr(telegram, "send_message", lambda **kwargs: calls.append(1) or "1")
    acknowledged(world)
    first = decide(world, django_capture_on_commit_callbacks, decision="monitor")
    second = decide(world, django_capture_on_commit_callbacks, decision="inspect_site")
    assert decision_event_key(first) != decision_event_key(second)
    assert len(calls) == 2
    assert SafetyTelegramDelivery.objects.count() == 2


def test_replayed_dispatch_reuses_the_same_delivery_row(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    calls = []
    monkeypatch.setattr(telegram, "send_message", lambda **kwargs: calls.append(1) or "1")
    acknowledged(world)
    alert = decide(world, django_capture_on_commit_callbacks)

    from apps.safety.telegram_delivery import _dispatch_decision, create_decision_deliveries

    assert create_decision_deliveries(alert) == []
    assert _dispatch_decision(alert.pk, decision_event_key(alert)) == 0
    assert len(calls) == 1
    assert SafetyTelegramDelivery.objects.count() == 1


def test_a_replayed_task_never_sends_a_second_message(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    calls = []
    monkeypatch.setattr(telegram, "send_message", lambda **kwargs: calls.append(1) or "1")
    acknowledged(world)
    decide(world, django_capture_on_commit_callbacks)
    delivery = SafetyTelegramDelivery.objects.get()

    assert deliver_safety_telegram_message(str(delivery.pk)) == "sent"
    assert len(calls) == 1


def test_users_without_a_destination_get_no_delivery_row(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    monkeypatch.setattr(telegram, "send_message", lambda **kwargs: "1")
    acknowledged(world)
    decide(world, django_capture_on_commit_callbacks)
    recipients = {d.recipient.user_id for d in SafetyTelegramDelivery.objects.all()}
    assert recipients == {world["cm"].pk}


# --------------------------------------------------------------------------
# Disabled and unconfigured states
# --------------------------------------------------------------------------


def test_disabled_by_default_writes_nothing_and_sends_nothing(
    world, django_capture_on_commit_callbacks, settings
):
    assert settings.SAFETY_TELEGRAM_ENABLED is False
    acknowledged(world)
    decide(world, django_capture_on_commit_callbacks)
    assert SafetyTelegramDelivery.all_objects.count() == 0


def test_enabled_without_a_token_records_a_skip_and_sends_nothing(
    world, telegram_on, django_capture_on_commit_callbacks
):
    telegram_on.SAFETY_TELEGRAM_BOT_TOKEN = ""
    acknowledged(world)
    decide(world, django_capture_on_commit_callbacks)
    delivery = SafetyTelegramDelivery.objects.get()
    assert delivery.status == SafetyTelegramDelivery.Status.SKIPPED
    assert delivery.failure_code == "telegram_not_configured"
    assert delivery.sent_at is None


def test_disabled_destination_records_a_skip(
    world, telegram_on, django_capture_on_commit_callbacks
):
    world["cm_chat"].is_enabled = False
    world["cm_chat"].save(update_fields=["is_enabled"])
    acknowledged(world)
    decide(world, django_capture_on_commit_callbacks)
    delivery = SafetyTelegramDelivery.objects.get()
    assert delivery.status == SafetyTelegramDelivery.Status.SKIPPED
    assert delivery.failure_code == "telegram_recipient_disabled"


def test_switching_off_between_queueing_and_running_skips_the_send(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    monkeypatch.setattr(telegram, "send_message", lambda **kwargs: "1")
    acknowledged(world)
    alert = decide(world, django_capture_on_commit_callbacks)
    SafetyTelegramDelivery.all_objects.update(
        status=SafetyTelegramDelivery.Status.QUEUED,
        sent_at=None,
        attempt_count=0,
    )
    delivery = SafetyTelegramDelivery.objects.get()
    telegram_on.SAFETY_TELEGRAM_ENABLED = False

    assert deliver_safety_telegram_message(str(delivery.pk)) == "skipped"
    delivery.refresh_from_db()
    assert delivery.failure_code == "telegram_disabled"
    assert alert.status == ProjectSafetyAlert.Status.ACTIONED


def test_a_superseded_decision_is_not_delivered(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    monkeypatch.setattr(telegram, "send_message", lambda **kwargs: "1")
    acknowledged(world)
    alert = decide(world, django_capture_on_commit_callbacks)
    delivery = SafetyTelegramDelivery.objects.get()
    SafetyTelegramDelivery.all_objects.filter(pk=delivery.pk).update(
        status=SafetyTelegramDelivery.Status.QUEUED,
        sent_at=None,
    )
    close_alert(alert_id=alert.pk, actor=world["cm"], notes="Resolved.")

    assert deliver_safety_telegram_message(str(delivery.pk)) == "skipped"
    delivery.refresh_from_db()
    assert delivery.failure_code == "telegram_decision_superseded"


# --------------------------------------------------------------------------
# Client behaviour: response classification, all offline
# --------------------------------------------------------------------------


def test_client_returns_the_message_id_on_success(telegram_on, monkeypatch):
    opener = install_opener(
        monkeypatch,
        response=FakeResponse(payload={"ok": True, "result": {"message_id": 77}}),
    )
    assert telegram.send_message(chat_id="123456789", text="مرحبا") == "77"
    request = opener.requests[0]
    assert request.full_url.startswith("https://api.telegram.org/bot")
    body = json.loads(request.data.decode("utf-8"))
    assert body["chat_id"] == "123456789"
    assert body["disable_web_page_preview"] is True


@pytest.mark.parametrize(
    ("status", "payload", "code", "retryable"),
    [
        (429, {"parameters": {"retry_after": 12}}, "telegram_rate_limited", True),
        (500, {}, "telegram_http_500", True),
        (503, {}, "telegram_http_503", True),
        (401, {}, "telegram_invalid_token", False),
        (404, {}, "telegram_invalid_token", False),
        (403, {"description": "Forbidden: bot was blocked by the user"},
         "telegram_invalid_chat", False),
        (400, {"description": "Bad Request: chat not found"}, "telegram_invalid_chat", False),
        (400, {"description": "Bad Request: message text is empty"},
         "telegram_invalid_request", False),
        (418, {}, "telegram_http_418", False),
    ],
)
def test_client_classifies_http_failures(
    telegram_on, monkeypatch, status, payload, code, retryable
):
    install_opener(monkeypatch, error=http_error(status, payload))
    with pytest.raises(telegram.TelegramError) as exc:
        telegram.send_message(chat_id="123456789", text="x")
    assert exc.value.code == code
    assert exc.value.retryable is retryable
    assert FAKE_TOKEN not in str(exc.value)


def test_client_classifies_timeouts_and_connection_failures(telegram_on, monkeypatch):
    install_opener(monkeypatch, error=TimeoutError())
    with pytest.raises(telegram.TelegramError) as exc:
        telegram.send_message(chat_id="123456789", text="x")
    assert (exc.value.code, exc.value.retryable) == ("telegram_timeout", True)

    install_opener(monkeypatch, error=urllib.error.URLError("unreachable"))
    with pytest.raises(telegram.TelegramError) as exc:
        telegram.send_message(chat_id="123456789", text="x")
    assert (exc.value.code, exc.value.retryable) == ("telegram_network_error", True)


def test_client_rejects_an_ok_false_body(telegram_on, monkeypatch):
    install_opener(
        monkeypatch,
        response=FakeResponse(payload={"ok": False, "error_code": 400,
                                       "description": "Bad Request: chat not found"}),
    )
    with pytest.raises(telegram.TelegramError) as exc:
        telegram.send_message(chat_id="123456789", text="x")
    assert exc.value.code == "telegram_invalid_chat"


def test_client_refuses_to_send_when_disabled_or_unconfigured(settings, monkeypatch):
    install_opener(monkeypatch, response=FakeResponse())
    settings.SAFETY_TELEGRAM_ENABLED = False
    settings.SAFETY_TELEGRAM_BOT_TOKEN = FAKE_TOKEN
    with pytest.raises(telegram.TelegramNotConfigured):
        telegram.send_message(chat_id="123456789", text="x")

    settings.SAFETY_TELEGRAM_ENABLED = True
    settings.SAFETY_TELEGRAM_BOT_TOKEN = ""
    with pytest.raises(telegram.TelegramNotConfigured):
        telegram.send_message(chat_id="123456789", text="x")


def test_client_refuses_a_non_https_base_url(telegram_on, monkeypatch):
    install_opener(monkeypatch, response=FakeResponse())
    telegram_on.SAFETY_TELEGRAM_API_BASE_URL = "http://api.telegram.org"
    with pytest.raises(telegram.TelegramNotConfigured) as exc:
        telegram.send_message(chat_id="123456789", text="x")
    assert exc.value.code == "telegram_endpoint_invalid"


# --------------------------------------------------------------------------
# Task-level retry and failure handling
# --------------------------------------------------------------------------


def queued_delivery(world, django_capture_on_commit_callbacks, monkeypatch):
    monkeypatch.setattr(telegram, "send_message", lambda **kwargs: "1")
    acknowledged(world)
    decide(world, django_capture_on_commit_callbacks)
    SafetyTelegramDelivery.all_objects.update(
        status=SafetyTelegramDelivery.Status.QUEUED,
        sent_at=None,
        attempt_count=0,
        provider_message_id="",
    )
    return SafetyTelegramDelivery.objects.get()


def test_permanent_failure_marks_the_delivery_failed_without_retrying(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    delivery = queued_delivery(world, django_capture_on_commit_callbacks, monkeypatch)

    def boom(**kwargs):
        raise telegram.TelegramError("telegram_invalid_chat", retryable=False)

    monkeypatch.setattr(telegram, "send_message", boom)
    assert deliver_safety_telegram_message(str(delivery.pk)) == "failed"
    delivery.refresh_from_db()
    assert delivery.failure_code == "telegram_invalid_chat"
    assert delivery.sent_at is None
    assert delivery.attempt_count == 1


def test_retryable_failure_requeues_the_delivery(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    from apps.safety.telegram_tasks import TransientTelegramDeliveryError

    delivery = queued_delivery(world, django_capture_on_commit_callbacks, monkeypatch)

    def boom(**kwargs):
        raise telegram.TelegramError("telegram_http_500", retryable=True)

    monkeypatch.setattr(telegram, "send_message", boom)
    # Called directly, Celery re-raises what retry() was given: the sanitized
    # code, never the provider error that carries the token-bearing URL.
    with pytest.raises(TransientTelegramDeliveryError) as exc:
        deliver_safety_telegram_message(str(delivery.pk))
    assert str(exc.value) == "telegram_http_500"
    assert FAKE_TOKEN not in str(exc.value)
    delivery.refresh_from_db()
    assert delivery.status == SafetyTelegramDelivery.Status.QUEUED
    assert delivery.failure_code == "telegram_http_500"
    assert delivery.sent_at is None


def test_exhausted_retries_end_as_failed(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    delivery = queued_delivery(world, django_capture_on_commit_callbacks, monkeypatch)
    telegram_on.SAFETY_TELEGRAM_MAX_RETRIES = 0

    def boom(**kwargs):
        raise telegram.TelegramError("telegram_timeout", retryable=True)

    monkeypatch.setattr(telegram, "send_message", boom)
    assert deliver_safety_telegram_message(str(delivery.pk)) == "failed"
    delivery.refresh_from_db()
    assert delivery.failure_code == "telegram_timeout"


def test_an_unexpected_client_error_is_contained(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    delivery = queued_delivery(world, django_capture_on_commit_callbacks, monkeypatch)

    def boom(**kwargs):
        raise RuntimeError(f"leaky {FAKE_TOKEN}")

    monkeypatch.setattr(telegram, "send_message", boom)
    assert deliver_safety_telegram_message(str(delivery.pk)) == "failed"
    delivery.refresh_from_db()
    assert delivery.failure_code == "telegram_unexpected_error"
    assert FAKE_TOKEN not in delivery.failure_code


def test_a_live_claim_is_left_to_its_owner_and_a_stale_one_is_reclaimed(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    from datetime import timedelta

    from apps.safety.telegram_tasks import TELEGRAM_STALE_CLAIM_SECONDS

    delivery = queued_delivery(world, django_capture_on_commit_callbacks, monkeypatch)
    SafetyTelegramDelivery.all_objects.filter(pk=delivery.pk).update(
        status=SafetyTelegramDelivery.Status.PROCESSING,
        processing_started_at=timezone.now(),
    )
    calls = []
    monkeypatch.setattr(telegram, "send_message", lambda **kwargs: calls.append(1) or "9")
    assert deliver_safety_telegram_message(str(delivery.pk)) == "processing"
    assert calls == []

    SafetyTelegramDelivery.all_objects.filter(pk=delivery.pk).update(
        processing_started_at=timezone.now()
        - timedelta(seconds=TELEGRAM_STALE_CLAIM_SECONDS + 60),
    )
    assert deliver_safety_telegram_message(str(delivery.pk)) == "sent"
    assert len(calls) == 1


def test_a_terminal_delivery_is_never_resent(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    delivery = queued_delivery(world, django_capture_on_commit_callbacks, monkeypatch)
    SafetyTelegramDelivery.all_objects.filter(pk=delivery.pk).update(
        status=SafetyTelegramDelivery.Status.FAILED,
    )
    calls = []
    monkeypatch.setattr(telegram, "send_message", lambda **kwargs: calls.append(1) or "1")
    assert deliver_safety_telegram_message(str(delivery.pk)) == "failed"
    assert calls == []


def test_a_missing_delivery_is_not_an_error(telegram_on):
    assert deliver_safety_telegram_message("11111111-1111-4111-8111-111111111111") == "missing"


# --------------------------------------------------------------------------
# Failure isolation and secret hygiene
# --------------------------------------------------------------------------


def test_a_telegram_failure_never_rolls_back_the_decision(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    def boom(**kwargs):
        raise RuntimeError("telegram exploded")

    monkeypatch.setattr(telegram, "send_message", boom)
    acknowledged(world)
    alert = decide(world, django_capture_on_commit_callbacks, decision="inspect_site")
    assert alert.status == ProjectSafetyAlert.Status.ACTIONED
    assert alert.decision == "inspect_site"
    assert alert.decided_by_id == world["admin"].pk


def test_a_dispatch_failure_is_swallowed_and_logged_without_the_token(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch, caplog
):
    from apps.safety import telegram_delivery

    def boom(alert):
        raise RuntimeError("recipient lookup failed")

    monkeypatch.setattr(telegram_delivery, "_decision_recipients", boom)
    with caplog.at_level(logging.ERROR):
        acknowledged(world)
        alert = decide(world, django_capture_on_commit_callbacks)
    assert alert.status == ProjectSafetyAlert.Status.ACTIONED
    assert FAKE_TOKEN not in caplog.text


def test_no_audit_entry_or_stored_field_contains_the_token(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    monkeypatch.setattr(telegram, "send_message", lambda **kwargs: "55")
    acknowledged(world)
    decide(world, django_capture_on_commit_callbacks, decision="monitor")
    serialized = json.dumps(
        [
            {
                "action": entry.action,
                "entity_ref": entry.entity_ref,
                "before": entry.before,
                "after": entry.after,
            }
            for entry in AuditLog.objects.all()
        ],
        default=str,
    )
    assert FAKE_TOKEN not in serialized
    assert "telegram" not in serialized.lower()
    assert "chat" not in serialized.lower()
    delivery = SafetyTelegramDelivery.objects.get()
    assert FAKE_TOKEN not in json.dumps(
        {
            "failure_code": delivery.failure_code,
            "provider_message_id": delivery.provider_message_id,
            "event_key": delivery.event_key,
        }
    )


def test_no_telegram_rest_endpoint_is_exposed():
    """Provisioning is Django Admin only; the API exposes no Telegram surface."""

    from django.urls import get_resolver

    def walk(resolver, prefix=""):
        for pattern in resolver.url_patterns:
            route = prefix + str(getattr(pattern, "pattern", ""))
            if hasattr(pattern, "url_patterns"):
                yield from walk(pattern, route)
            else:
                yield route

    api_routes = [route for route in walk(get_resolver()) if route.startswith("api/")]
    assert api_routes, "Expected the API URLconf to be discoverable."
    forbidden = ("telegram", "broadcast", "notify", "send-telegram", "chat")
    assert not [
        route for route in api_routes if any(word in route.lower() for word in forbidden)
    ]


# --------------------------------------------------------------------------
# Message content
# --------------------------------------------------------------------------


def test_message_states_the_human_decision_without_provider_payload(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    monkeypatch.setattr(telegram, "send_message", lambda **kwargs: "1")
    acknowledged(world)
    alert = decide(
        world,
        django_capture_on_commit_callbacks,
        decision="suspend_outdoor_work",
        notes="حتى انتهاء الهزات الارتدادية.",
    )
    message = build_decision_message(alert)
    assert "قرار سلامة مسجَّل" in message
    assert "Construction site" in message
    assert "إيقاف الأعمال الخارجية مؤقتاً" in message
    assert "حتى انتهاء الهزات الارتدادية." in message
    assert world["admin"].full_name in message
    # No raw provider payload, no source link, no internal identifiers.
    assert "synthetic" not in message
    assert "http" not in message
    assert str(alert.pk) not in message
    assert str(alert.hazard_event_id) not in message


def test_message_escapes_html_and_respects_the_length_bound(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    project = world["alert"].project
    project.name = "<b>Tower</b> & Co <script>alert(1)</script>"
    project.save(update_fields=["name"])
    monkeypatch.setattr(telegram, "send_message", lambda **kwargs: "1")
    acknowledged(world)
    alert = decide(
        world,
        django_capture_on_commit_callbacks,
        decision="other",
        notes="ملاحظة " * 200,
    )
    message = build_decision_message(alert)
    assert "&lt;script&gt;" in message
    assert "<script>" not in message
    assert "&amp; Co" in message
    assert len(message) <= telegram_on.SAFETY_TELEGRAM_MAX_MESSAGE_CHARS

    short = build_decision_message(alert, max_chars=500)
    assert len(short) <= 500


def test_event_key_is_deterministic_and_bounded(
    world, telegram_on, django_capture_on_commit_callbacks, monkeypatch
):
    monkeypatch.setattr(telegram, "send_message", lambda **kwargs: "1")
    acknowledged(world)
    alert = decide(world, django_capture_on_commit_callbacks)
    key = decision_event_key(alert)
    assert key == decision_event_key(ProjectSafetyAlert.objects.get(pk=alert.pk))
    assert key.startswith("action_decided:")
    assert alert.decision in key
    assert 0 < len(key) <= 120
