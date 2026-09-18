"""Outbound Telegram delivery of recorded human safety decisions.

The only trigger is a human transition to ``actioned`` in
:func:`apps.safety.services.decide_alert_action`. Provider ingestion, alert
creation, escalation, hazard withdrawal, expiry, polling, cron, the AI engine,
and the frontend never reach this module.

Delivery is scheduled with ``transaction.on_commit(..., robust=True)``: nothing
here runs inside the decision transaction, and no Telegram failure can roll the
decision back. The alert stays ``actioned`` whatever Telegram does.
"""

import html
import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from . import telegram
from .notifications import ACTION_LABELS_AR, HAZARD_LABELS_AR
from .recipients import alert_recipient_groups, project_telegram_destinations


logger = logging.getLogger(__name__)

SEVERITY_LABELS_AR = {
    "low": "منخفضة",
    "medium": "متوسطة",
    "high": "عالية",
    "critical": "حرجة",
}
DECISION_EVENT_PREFIX = "action_decided"
WORKER_INSTRUCTION_EVENT_PREFIX = "worker_protection_approved"
NOTES_MAX_CHARS = 500
TRUNCATION_SUFFIX = "…"

# Reasons a row is written but never sent. Codes are stable and contain no
# secrets, no chat ids, and no provider text.
SKIP_NOT_CONFIGURED = "telegram_not_configured"
SKIP_RECIPIENT_DISABLED = "telegram_recipient_disabled"


def decision_event_key(alert):
    """A stable identity for one recorded decision.

    Derived only from persisted alert state, so a Celery retry, a worker
    restart, or a duplicated task all compute the same key and collapse onto
    the same delivery row. A later, different decision moves ``decided_at``
    and therefore legitimately produces a new key.
    """

    decided_at = alert.decided_at
    stamp = decided_at.isoformat() if decided_at else ""
    return f"{DECISION_EVENT_PREFIX}:{stamp}:{alert.decision or ''}"[:120]


def _escape(value):
    return html.escape(str(value or ""), quote=False)


def build_decision_message(alert, *, max_chars=None):
    """Build the Arabic advisory message for a recorded decision.

    Factual and bounded: it states what a named manager decided and when. It
    carries no raw provider payload, no credentials, no internal identifiers,
    no links, and it never instructs anyone to act on the platform's behalf.
    """

    limit = max_chars or settings.SAFETY_TELEGRAM_MAX_MESSAGE_CHARS
    hazard = HAZARD_LABELS_AR.get(alert.hazard_type, alert.hazard_type)
    action = ACTION_LABELS_AR.get(alert.decision, alert.decision or "")
    severity = SEVERITY_LABELS_AR.get(alert.severity, alert.severity)
    decider = getattr(alert.decided_by, "full_name", "") or "المدير المسؤول"
    decided_at = timezone.localtime(alert.decided_at) if alert.decided_at else None
    lines = [
        "<b>قرار سلامة مسجَّل</b>",
        "",
        f"المشروع: {_escape(alert.project.name)}",
        f"الخطر: {_escape(hazard)}",
        f"مستوى الخطورة: {_escape(severity)}",
        f"المسافة من الموقع: {_escape(alert.distance_km)} كم",
        f"القرار المعتمد: {_escape(action)}",
        f"المسؤول عن القرار: {_escape(decider)}",
    ]
    if decided_at is not None:
        lines.append(f"وقت القرار: {_escape(decided_at.strftime('%Y-%m-%d %H:%M'))}")
    notes = (alert.decision_notes or "").strip()
    if notes:
        if len(notes) > NOTES_MAX_CHARS:
            notes = notes[: NOTES_MAX_CHARS - 1] + TRUNCATION_SUFFIX
        lines.append(f"ملاحظات: {_escape(notes)}")
    lines += [
        "",
        "رسالة إعلامية من نظام SFLMS تنقل قراراً اتخذه المدير المسؤول. "
        "التنفيذ والمتابعة يتمان عبر القنوات الرسمية للموقع.",
    ]
    message = "\n".join(lines)
    if len(message) > limit:
        # Cut on a character boundary; HTML tags are only in the fixed header,
        # so truncation cannot split one.
        message = message[: limit - len(TRUNCATION_SUFFIX)] + TRUNCATION_SUFFIX
    return message


def _decision_recipients(alert):
    """Configured Telegram destinations for the managers who own this alert."""

    from .models import SafetyTelegramRecipient

    seen = set()
    user_ids = []
    for group in alert_recipient_groups(alert):
        for user in group.users:
            if user.pk not in seen:
                seen.add(user.pk)
                user_ids.append(user.pk)
    if not user_ids:
        return []
    recipients = list(
        SafetyTelegramRecipient.objects.filter(user_id__in=user_ids)
        .select_related("user")
        .order_by("pk")
    )
    return recipients


def create_decision_deliveries(alert, *, event_key=None):
    """Create one delivery row per configured destination. Idempotent.

    Returns the ids of rows that are queued for an actual send. Rows already
    present (a replayed task, a duplicated commit hook) are never re-queued.
    """

    from .models import SafetyTelegramDelivery

    event_key = event_key or decision_event_key(alert)
    configured = telegram.is_configured()
    queued_ids = []
    for recipient in _decision_recipients(alert):
        if not recipient.is_enabled:
            status = SafetyTelegramDelivery.Status.SKIPPED
            failure_code = SKIP_RECIPIENT_DISABLED
        elif not configured:
            status = SafetyTelegramDelivery.Status.SKIPPED
            failure_code = SKIP_NOT_CONFIGURED
        else:
            status = SafetyTelegramDelivery.Status.QUEUED
            failure_code = ""
        try:
            with transaction.atomic():
                delivery, created = SafetyTelegramDelivery.all_objects.get_or_create(
                    alert=alert,
                    recipient=recipient,
                    event_key=event_key,
                    defaults={"status": status, "failure_code": failure_code},
                )
        except IntegrityError:
            # A concurrent worker created the same row; that row owns the send.
            continue
        if created and delivery.status == SafetyTelegramDelivery.Status.QUEUED:
            queued_ids.append(delivery.pk)
    return queued_ids


def _dispatch_decision(alert_id, event_key):
    from .models import ProjectSafetyAlert
    from .telegram_tasks import deliver_safety_telegram_message

    try:
        if not settings.SAFETY_TELEGRAM_ENABLED:
            # Switched off: no row, no queue entry, no external side effect.
            return 0
        alert = (
            ProjectSafetyAlert.objects.select_related("project", "decided_by")
            .filter(pk=alert_id, status=ProjectSafetyAlert.Status.ACTIONED)
            .first()
        )
        if alert is None or decision_event_key(alert) != event_key:
            # The decision was superseded before the hook ran; the newer
            # decision has scheduled its own delivery.
            return 0
        queued_ids = create_decision_deliveries(alert, event_key=event_key)
        for delivery_id in queued_ids:
            deliver_safety_telegram_message.delay(str(delivery_id))
        return len(queued_ids)
    except Exception:
        logger.exception(
            "Safety Telegram dispatch failed.",
            extra={"alert_id": str(alert_id)},
        )
        return 0


def schedule_decision_delivery(alert):
    """Queue Telegram delivery to run after the decision transaction commits."""

    alert_id = alert.pk
    event_key = decision_event_key(alert)
    transaction.on_commit(lambda: _dispatch_decision(alert_id, event_key), robust=True)


# ---------------------------------------------------------------------------
# Approved worker-protection instructions
# ---------------------------------------------------------------------------


def worker_instruction_event_key(proposal):
    """A stable identity for one approved worker-protection instruction.

    Derived from persisted approval state, so a retried task, a replayed commit
    hook, or a second approval attempt all compute the same key and collapse
    onto the same delivery row. Approving an already-approved proposal
    therefore cannot produce a second message.
    """

    reviewed_at = proposal.reviewed_at
    stamp = reviewed_at.isoformat() if reviewed_at else ""
    return f"{WORKER_INSTRUCTION_EVENT_PREFIX}:{proposal.pk}:{stamp}"[:120]


def _window_text(proposal):
    """The approved action's time window, or "" when it has none."""

    start = timezone.localtime(proposal.effective_from) if proposal.effective_from else None
    end = timezone.localtime(proposal.effective_until) if proposal.effective_until else None
    if start and end:
        same_day = start.date() == end.date()
        tail = end.strftime("%H:%M") if same_day else end.strftime("%Y-%m-%d %H:%M")
        return f"{start.strftime('%Y-%m-%d %H:%M')} — {tail}"
    if start:
        return f"من {start.strftime('%Y-%m-%d %H:%M')}"
    if end:
        return f"حتى {end.strftime('%Y-%m-%d %H:%M')}"
    return ""


def build_worker_instruction_message(proposal, *, max_chars=None):
    """The Arabic instruction sent to a project's crew channel after approval.

    States the hazard that prompted it, the approved action, the window it
    applies for, the reason, and that a General Manager approved it through
    SFLMS. It carries no provider payload, no credentials, no database
    identifiers and no links, and it is only ever built for a proposal already
    approved by a General Manager.
    """

    limit = max_chars or settings.SAFETY_TELEGRAM_MAX_MESSAGE_CHARS
    alert = proposal.alert
    hazard = HAZARD_LABELS_AR.get(alert.hazard_type, alert.hazard_type)
    action = ACTION_LABELS_AR.get(proposal.proposed_action, proposal.proposed_action or "")
    severity = SEVERITY_LABELS_AR.get(alert.severity, alert.severity)
    lines = [
        "🚨 <b>قرار سلامة معتمد — SFLMS</b>",
        "",
        f"المشروع: {_escape(alert.project.name)}",
        f"الخطر: {_escape(hazard)}",
        f"مستوى الخطورة: {_escape(severity)}",
        "",
        f"الإجراء المعتمد: {_escape(action)}",
    ]
    window = _window_text(proposal)
    if window:
        lines.append(f"سريان القرار: {_escape(window)}")
    if proposal.worker_scope:
        lines.append(f"الفئات المشمولة: {_escape(proposal.worker_scope)}")
    notes = (proposal.proposal_notes or "").strip()
    if notes:
        if len(notes) > NOTES_MAX_CHARS:
            notes = notes[: NOTES_MAX_CHARS - 1] + TRUNCATION_SUFFIX
        lines += ["", f"السبب: {_escape(notes)}"]
    lines += [
        "",
        "التعليمات: التزموا بالإجراء المعتمد خلال المدة المحددة.",
        "",
        "قرار معتمد من الإدارة عبر نظام SFLMS. "
        "التنفيذ والمتابعة يتمان عبر القنوات الرسمية للموقع.",
    ]
    message = "\n".join(lines)
    if len(message) > limit:
        message = message[: limit - len(TRUNCATION_SUFFIX)] + TRUNCATION_SUFFIX
    return message


def create_worker_instruction_deliveries(proposal, *, event_key=None):
    """One delivery row per destination of the affected project. Idempotent.

    A project with no configured destination produces no rows; the caller
    records that, so "nobody was reachable" is observable rather than looking
    like a successful send.
    """

    from .models import SafetyTelegramDelivery

    event_key = event_key or worker_instruction_event_key(proposal)
    configured = telegram.is_configured()
    queued_ids = []
    for destination in project_telegram_destinations(proposal.alert.project):
        if not configured:
            status = SafetyTelegramDelivery.Status.SKIPPED
            failure_code = SKIP_NOT_CONFIGURED
        else:
            status = SafetyTelegramDelivery.Status.QUEUED
            failure_code = ""
        try:
            with transaction.atomic():
                delivery, created = SafetyTelegramDelivery.all_objects.get_or_create(
                    alert=proposal.alert,
                    project_destination=destination,
                    event_key=event_key,
                    defaults={
                        "status": status,
                        "failure_code": failure_code,
                        "proposal": proposal,
                    },
                )
        except IntegrityError:
            # A concurrent worker created the same row; that row owns the send.
            continue
        if created and delivery.status == SafetyTelegramDelivery.Status.QUEUED:
            queued_ids.append(delivery.pk)
    return queued_ids


def _dispatch_worker_instruction(proposal_id, event_key):
    from .models import SafetyActionProposal
    from .telegram_tasks import deliver_safety_telegram_message

    try:
        if not settings.SAFETY_TELEGRAM_ENABLED:
            return 0
        proposal = (
            SafetyActionProposal.objects.select_related(
                "alert__project", "alert__hazard_event", "reviewed_by"
            )
            .filter(
                pk=proposal_id,
                status=SafetyActionProposal.Status.APPROVED,
                decision_type=SafetyActionProposal.DecisionType.WORKER_PROTECTION,
            )
            .first()
        )
        if proposal is None or worker_instruction_event_key(proposal) != event_key:
            return 0
        if not project_telegram_destinations(proposal.alert.project):
            # The decision stands and stays approved; it simply has nowhere to
            # go. Logged so an unreachable project is visible rather than
            # looking like a delivery that quietly succeeded.
            logger.warning(
                "Approved worker instruction has no Telegram destination for its project.",
                extra={
                    "proposal_id": str(proposal_id),
                    "project_id": str(proposal.alert.project_id),
                },
            )
            return 0
        queued_ids = create_worker_instruction_deliveries(proposal, event_key=event_key)
        for delivery_id in queued_ids:
            deliver_safety_telegram_message.delay(str(delivery_id))
        return len(queued_ids)
    except Exception:
        logger.exception(
            "Safety worker-instruction dispatch failed.",
            extra={"proposal_id": str(proposal_id)},
        )
        return 0


def schedule_worker_instruction_delivery(proposal):
    """Queue the approved instruction to run after the approval commits."""

    proposal_id = proposal.pk
    event_key = worker_instruction_event_key(proposal)
    transaction.on_commit(
        lambda: _dispatch_worker_instruction(proposal_id, event_key), robust=True
    )
