"""The Celery task that sends one recorded safety decision to Telegram.

Deliberately separate from ``apps/safety/tasks.py``: that module is provider
polling only, and an architecture guard asserts it cannot reach an operational
action. Registered with Celery from ``SafetyConfig.ready`` because Celery
autodiscovery imports only ``tasks``. There is no Beat entry: this task runs
only when a human decision enqueues it.
"""

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import telegram
from .telegram_delivery import (
    SKIP_NOT_CONFIGURED,
    SKIP_RECIPIENT_DISABLED,
    build_decision_message,
    build_worker_instruction_message,
    decision_event_key,
    worker_instruction_event_key,
)


def _worker_instruction_text(delivery):
    """The approved instruction for this row, or None if it no longer stands.

    Re-read under the task rather than trusted from the row: a proposal that is
    no longer an approved worker-protection proposal must not be sent, whatever
    was true when the row was written.
    """

    from .models import SafetyActionProposal

    proposal = (
        SafetyActionProposal.objects.select_related(
            "alert__project", "alert__hazard_event", "reviewed_by"
        )
        .filter(
            pk=delivery.proposal_id,
            status=SafetyActionProposal.Status.APPROVED,
            decision_type=SafetyActionProposal.DecisionType.WORKER_PROTECTION,
        )
        .first()
    )
    if proposal is None or worker_instruction_event_key(proposal) != delivery.event_key:
        return None
    return build_worker_instruction_message(proposal)


# Decorator ceiling; the configured SAFETY_TELEGRAM_MAX_RETRIES (0-5) applies.
TELEGRAM_TASK_MAX_RETRIES = 5
TELEGRAM_MAX_RETRY_COUNTDOWN = 300
# A claim older than this belonged to a worker that died mid-send.
TELEGRAM_STALE_CLAIM_SECONDS = 600


class TransientTelegramDeliveryError(RuntimeError):
    """Carries only a short failure code, never provider detail."""


def _finish_telegram_delivery(delivery_id, status, *, failure_code="", message_id=""):
    from .models import SafetyTelegramDelivery

    SafetyTelegramDelivery.all_objects.filter(pk=delivery_id).update(
        status=status,
        failure_code=failure_code,
        provider_message_id=message_id,
        processing_started_at=None,
        sent_at=timezone.now() if status == SafetyTelegramDelivery.Status.SENT else None,
        updated_at=timezone.now(),
    )


def _claim_telegram_delivery(delivery_id):
    """Take exclusive ownership of one delivery row, or return None.

    Terminal rows and live claims held by another worker are left alone, which
    is what makes at-least-once task execution safe: a replayed task can never
    produce a second Telegram message for the same decision.
    """

    from .models import SafetyTelegramDelivery

    terminal = {
        SafetyTelegramDelivery.Status.SENT,
        SafetyTelegramDelivery.Status.FAILED,
        SafetyTelegramDelivery.Status.SKIPPED,
    }
    stale_before = timezone.now() - timedelta(seconds=TELEGRAM_STALE_CLAIM_SECONDS)
    with transaction.atomic():
        delivery = (
            # Lock only this row; the nullable joins cannot be locked on PostgreSQL.
            SafetyTelegramDelivery.all_objects.select_for_update(of=("self",))
            .select_related(
                "recipient__user",
                "project_destination",
                "alert__project",
                "alert__decided_by",
            )
            .filter(pk=delivery_id)
            .first()
        )
        if delivery is None or delivery.status in terminal:
            return delivery, None
        if (
            delivery.status == SafetyTelegramDelivery.Status.PROCESSING
            and delivery.processing_started_at
            and delivery.processing_started_at > stale_before
        ):
            return delivery, None
        delivery.status = SafetyTelegramDelivery.Status.PROCESSING
        delivery.processing_started_at = timezone.now()
        delivery.attempt_count += 1
        delivery.failure_code = ""
        delivery.save(
            update_fields=[
                "status",
                "processing_started_at",
                "attempt_count",
                "failure_code",
                "updated_at",
            ]
        )
    return delivery, delivery


@shared_task(
    bind=True,
    name="safety.deliver_telegram_message",
    max_retries=TELEGRAM_TASK_MAX_RETRIES,
    acks_late=True,
)
def deliver_safety_telegram_message(self, delivery_id):
    """Send one recorded safety decision to one Telegram destination.

    Never raises into the Safety workflow: every outcome is written to the
    delivery row, and the alert it belongs to stays ``actioned`` regardless.
    """

    from .models import ProjectSafetyAlert, SafetyTelegramDelivery

    delivery, claimed = _claim_telegram_delivery(delivery_id)
    if delivery is None:
        return "missing"
    if claimed is None:
        return delivery.status

    if not settings.SAFETY_TELEGRAM_ENABLED:
        # Switched off between queueing and running: record, send nothing.
        _finish_telegram_delivery(
            delivery.pk,
            SafetyTelegramDelivery.Status.SKIPPED,
            failure_code="telegram_disabled",
        )
        return SafetyTelegramDelivery.Status.SKIPPED
    # One row addresses exactly one audience: a manager's own destination, or
    # an affected project's crew channel.
    audience = delivery.recipient or delivery.project_destination
    if audience is None or not (audience.is_active and audience.is_enabled):
        _finish_telegram_delivery(
            delivery.pk,
            SafetyTelegramDelivery.Status.SKIPPED,
            failure_code=SKIP_RECIPIENT_DISABLED,
        )
        return SafetyTelegramDelivery.Status.SKIPPED
    if not telegram.is_configured():
        _finish_telegram_delivery(
            delivery.pk,
            SafetyTelegramDelivery.Status.SKIPPED,
            failure_code=SKIP_NOT_CONFIGURED,
        )
        return SafetyTelegramDelivery.Status.SKIPPED
    alert = delivery.alert
    if delivery.proposal_id:
        # An approved worker-protection instruction: its authority is the
        # approval, so it is validated against the proposal, not the alert.
        text = _worker_instruction_text(delivery)
    elif (
        alert.status != ProjectSafetyAlert.Status.ACTIONED
        or decision_event_key(alert) != delivery.event_key
    ):
        # The decision this row describes is no longer the current one.
        text = None
    else:
        text = build_decision_message(alert)
    if text is None:
        _finish_telegram_delivery(
            delivery.pk,
            SafetyTelegramDelivery.Status.SKIPPED,
            failure_code="telegram_decision_superseded",
        )
        return SafetyTelegramDelivery.Status.SKIPPED

    try:
        message_id = telegram.send_message(
            chat_id=audience.chat_id,
            text=text,
        )
    except telegram.TelegramError as exc:
        max_retries = settings.SAFETY_TELEGRAM_MAX_RETRIES
        if exc.retryable and self.request.retries < max_retries:
            _finish_telegram_delivery(
                delivery.pk,
                SafetyTelegramDelivery.Status.QUEUED,
                failure_code=exc.code,
            )
            countdown = exc.retry_after or min(
                TELEGRAM_MAX_RETRY_COUNTDOWN,
                2 ** (self.request.retries + 1),
            )
            raise self.retry(
                # A sanitized code, never the original error: urllib attaches
                # the token-bearing URL to its exceptions.
                exc=TransientTelegramDeliveryError(exc.code),
                countdown=min(countdown, TELEGRAM_MAX_RETRY_COUNTDOWN),
            )
        _finish_telegram_delivery(
            delivery.pk,
            SafetyTelegramDelivery.Status.FAILED,
            failure_code=exc.code,
        )
        return SafetyTelegramDelivery.Status.FAILED
    except Exception:
        # Sanitized: the original may carry the bot token in its URL.
        _finish_telegram_delivery(
            delivery.pk,
            SafetyTelegramDelivery.Status.FAILED,
            failure_code="telegram_unexpected_error",
        )
        return SafetyTelegramDelivery.Status.FAILED

    _finish_telegram_delivery(
        delivery.pk,
        SafetyTelegramDelivery.Status.SENT,
        message_id=message_id,
    )
    return SafetyTelegramDelivery.Status.SENT
