"""The human decision workflow over an external hazard.

An external hazard is information. It never becomes an instruction on its own:
a responsible manager proposes a protective action, and a General Manager /
Super Admin approves or rejects it. Nothing is dispatched while a proposal is
open, and only an approved ``worker_protection`` proposal can reach a person.

The two workflows stay separate end to end:

* ``worker_protection`` -- proposed by the Construction Manager for the
  project's site personnel. On approval the alert makes the existing
  ``actioned`` transition and the approved instruction is queued for the
  assignment-scoped personnel who opted in.
* ``asset_protection`` -- proposed by the Operations Manager for the facility's
  equipment. On approval the decision is recorded and audited. No message is
  sent, and no asset is shut down, suspended, or altered: acting on the
  decision remains an explicit operation elsewhere in the platform.

This module owns authorization, the proposal state machine, and semantic audit.
The REST layer is a thin caller.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services import record_audit
from apps.notifications.models import Notification
from apps.notifications.services import notify_user

from .models import ProjectSafetyAlert, SafetyActionProposal
from .recipients import user_can_approve_safety, user_can_propose
from .telegram_delivery import schedule_worker_instruction_delivery


MAX_NOTES_LENGTH = 2000
MAX_SCOPE_LENGTH = 255

REJECTION_TITLE_AR = {
    "worker_protection": "تم رفض طلب حماية العاملين",
    "asset_protection": "تم رفض طلب حماية الأصول",
}
PROPOSAL_HREF = "/operations/safety-alerts/{alert_id}"

# A proposal may be raised while the alert is still being triaged, but never
# once it has been closed out or dismissed -- those are finished alerts.
PROPOSABLE_ALERT_STATUSES = frozenset(
    {
        ProjectSafetyAlert.Status.NEW,
        ProjectSafetyAlert.Status.ACKNOWLEDGED,
        ProjectSafetyAlert.Status.ACTIONED,
    }
)


def _clean_notes(value, field_name, *, required):
    text = (value or "").strip()
    if required and not text:
        raise ValidationError({field_name: "This field is required."})
    if len(text) > MAX_NOTES_LENGTH:
        raise ValidationError(
            {field_name: f"Ensure this field has no more than {MAX_NOTES_LENGTH} characters."}
        )
    if any(ord(character) < 32 and character not in "\n\r\t" for character in text):
        raise ValidationError({field_name: "Control characters are not allowed."})
    return text


def _proposal_audit_state(proposal):
    return {
        "status": proposal.status,
        "decision_type": proposal.decision_type,
        "proposed_action": proposal.proposed_action,
        "proposed_by": str(proposal.proposed_by_id) if proposal.proposed_by_id else None,
        "reviewed_by": str(proposal.reviewed_by_id) if proposal.reviewed_by_id else None,
        "reviewed_at": proposal.reviewed_at.isoformat() if proposal.reviewed_at else None,
    }


def _locked_proposal(proposal_id):
    return (
        SafetyActionProposal.all_objects.select_for_update(of=("self",))
        .select_related("alert__project", "alert__hazard_event", "proposed_by")
        .get(pk=proposal_id, is_active=True)
    )


def _require_active_actor(actor):
    if actor is None or not getattr(actor, "pk", None) or not actor.is_active:
        raise ValidationError({"actor": "An active authenticated actor is required."})


@transaction.atomic
def create_proposal(
    *,
    alert_id,
    actor,
    decision_type,
    proposed_action,
    notes,
    asset_ids=(),
    effective_from=None,
    effective_until=None,
    worker_scope="",
    request=None,
):
    """Record one manager's proposed protective action. Dispatches nothing."""

    _require_active_actor(actor)
    if decision_type not in SafetyActionProposal.DecisionType.values:
        raise ValidationError({"decision_type": "Select a supported decision type."})
    alert = (
        ProjectSafetyAlert.all_objects.select_related("project", "hazard_event")
        .get(pk=alert_id, is_active=True)
    )
    if not user_can_propose(actor, alert, decision_type):
        raise PermissionDenied("This user cannot propose this action for this safety alert.")
    if proposed_action not in ProjectSafetyAlert.Action.values:
        raise ValidationError({"proposed_action": "Select a supported safety action."})
    if alert.status not in PROPOSABLE_ALERT_STATUSES:
        raise ValidationError(
            {"status": "A proposal requires an alert that is not closed or dismissed."}
        )
    notes = _clean_notes(notes, "notes", required=True)

    assets = _validated_assets(alert, decision_type, asset_ids)
    proposal = SafetyActionProposal(
        alert=alert,
        decision_type=decision_type,
        proposed_action=proposed_action,
        proposal_notes=notes,
        effective_from=effective_from,
        effective_until=effective_until,
        worker_scope=(worker_scope or "").strip(),
        proposed_by=actor,
        proposed_at=timezone.now(),
    )
    proposal.full_clean(validate_unique=False, exclude={"affected_assets"})
    try:
        proposal.save()
    except IntegrityError as exc:
        # The partial unique index refused a second open proposal of this kind.
        raise ValidationError(
            {"decision_type": "An open proposal of this type already exists for this alert."}
        ) from exc
    if assets:
        proposal.affected_assets.set(assets)
    _acknowledge_for_proposal(alert, actor, request)

    record_audit(
        actor=actor,
        action=f"safety_proposal.{decision_type}.proposed",
        entity=proposal,
        before=None,
        after=_proposal_audit_state(proposal),
        request=request,
    )
    return proposal


def _acknowledge_for_proposal(alert, actor, request):
    """Raising a proposal is itself an acknowledgement of the alert.

    The alert lifecycle requires an alert to have been acknowledged before it
    can become ``actioned``, and a manager who has read the hazard closely
    enough to propose a response has plainly seen it. Recording it here keeps
    that existing invariant true without asking for a redundant second click,
    and it is audited with the same semantic action as the explicit step.
    """

    from .services import _alert_audit_state  # noqa: PLC0415 - avoids a cycle

    if alert.status != ProjectSafetyAlert.Status.NEW:
        return
    before = _alert_audit_state(alert)
    alert.status = ProjectSafetyAlert.Status.ACKNOWLEDGED
    alert.acknowledged_by = actor
    alert.acknowledged_at = timezone.now()
    alert.full_clean(validate_unique=False)
    alert.save(
        update_fields=["status", "acknowledged_by", "acknowledged_at", "updated_at"]
    )
    record_audit(
        actor=actor,
        action="safety_alert.acknowledged",
        entity=alert,
        before=before,
        after=_alert_audit_state(alert),
        request=request,
    )


def _validated_assets(alert, decision_type, asset_ids):
    """Assets named by an asset-protection proposal, confined to the facility."""

    from apps.assets.models import Asset

    asset_ids = [asset_id for asset_id in (asset_ids or []) if asset_id]
    if not asset_ids:
        return []
    if decision_type != SafetyActionProposal.DecisionType.ASSET_PROTECTION:
        raise ValidationError(
            {"asset_ids": "Only an asset-protection proposal can name affected assets."}
        )
    facility_id = alert.project.facility_id
    if not facility_id:
        raise ValidationError({"asset_ids": "This project has no facility."})
    assets = list(Asset.objects.filter(pk__in=asset_ids, facility_id=facility_id))
    if len(assets) != len(set(asset_ids)):
        # Naming an out-of-facility asset is refused outright rather than
        # silently narrowed, so the proposal always means what it says.
        raise ValidationError({"asset_ids": "Unknown asset for this project's facility."})
    return assets


def _require_approver(actor):
    _require_active_actor(actor)
    if not user_can_approve_safety(actor):
        raise PermissionDenied("This user cannot rule on safety action proposals.")


def _require_open(proposal, actor):
    if proposal.proposed_by_id == actor.pk:
        # Separation of duties: the ask and the ruling are different people.
        raise PermissionDenied("A proposal cannot be ruled on by the manager who raised it.")
    if not proposal.is_open:
        raise ValidationError(
            {"status": f"This proposal was already {proposal.status.replace('_', ' ')}."}
        )


@transaction.atomic
def approve_proposal(*, proposal_id, actor, notes="", request=None):
    """Accept a proposed protective action.

    Worker protection additionally moves the alert to ``actioned`` and queues
    the approved instruction for the project's opted-in personnel. Asset
    protection is recorded only: nothing is messaged and no asset is changed.
    """

    _require_approver(actor)
    proposal = _locked_proposal(proposal_id)
    _require_open(proposal, actor)
    notes = _clean_notes(notes, "notes", required=False)

    before = _proposal_audit_state(proposal)
    proposal.status = SafetyActionProposal.Status.APPROVED
    proposal.reviewed_by = actor
    proposal.reviewed_at = timezone.now()
    proposal.review_notes = notes
    proposal.full_clean(validate_unique=False, exclude={"affected_assets"})
    proposal.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "review_notes", "updated_at"]
    )
    record_audit(
        actor=actor,
        action=f"safety_proposal.{proposal.decision_type}.approved",
        entity=proposal,
        before=before,
        after=_proposal_audit_state(proposal),
        request=request,
    )

    if proposal.decision_type == SafetyActionProposal.DecisionType.WORKER_PROTECTION:
        _apply_worker_protection(proposal, actor, request)
    return proposal


def _apply_worker_protection(proposal, actor, request):
    """Record the approved decision on the alert and queue the instruction.

    Reuses the alert's existing ``actioned`` state rather than introducing a
    parallel one, so the lifecycle the rest of the platform reads stays true.
    """

    from .services import _alert_audit_state  # noqa: PLC0415 - avoids a cycle

    alert = proposal.alert
    before = _alert_audit_state(alert)
    alert.status = ProjectSafetyAlert.Status.ACTIONED
    alert.decision = proposal.proposed_action
    alert.decision_notes = proposal.proposal_notes
    alert.decided_by = actor
    alert.decided_at = proposal.reviewed_at
    alert.full_clean(validate_unique=False)
    alert.save(
        update_fields=[
            "status",
            "decision",
            "decision_notes",
            "decided_by",
            "decided_at",
            "updated_at",
        ]
    )
    record_audit(
        actor=actor,
        action="safety_alert.action_decided",
        entity=alert,
        before=before,
        after=_alert_audit_state(alert),
        request=request,
    )
    # Post-commit: no Telegram outcome can roll the approval back.
    schedule_worker_instruction_delivery(proposal)


@transaction.atomic
def reject_proposal(*, proposal_id, actor, reason, request=None):
    """Refuse a proposed protective action. Nothing is dispatched, ever."""

    _require_approver(actor)
    proposal = _locked_proposal(proposal_id)
    _require_open(proposal, actor)
    reason = _clean_notes(reason, "reason", required=True)

    before = _proposal_audit_state(proposal)
    proposal.status = SafetyActionProposal.Status.REJECTED
    proposal.reviewed_by = actor
    proposal.reviewed_at = timezone.now()
    proposal.review_notes = reason
    proposal.full_clean(validate_unique=False, exclude={"affected_assets"})
    proposal.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "review_notes", "updated_at"]
    )
    record_audit(
        actor=actor,
        action=f"safety_proposal.{proposal.decision_type}.rejected",
        entity=proposal,
        before=before,
        after=_proposal_audit_state(proposal),
        request=request,
    )
    _notify_proposer_of_rejection(proposal)
    return proposal


def _notify_proposer_of_rejection(proposal):
    """Tell the manager who raised it, in the app, with the reason.

    A refusal that nobody sees is a refusal the proposer will chase by hand, so
    the reason travels with it. Delivery is in-app only: rejections never reach
    a project's crew channel.
    """

    label = REJECTION_TITLE_AR.get(proposal.decision_type, "تم رفض طلب الحماية")
    notify_user(
        proposal.proposed_by,
        title=label,
        body=f"السبب: {proposal.review_notes}",
        category=Notification.Category.SAFETY,
        tone=Notification.Tone.WARNING,
        href=PROPOSAL_HREF.format(alert_id=proposal.alert_id),
        source=proposal,
        # Stable per ruling, so a retry cannot post the same refusal twice.
        deduplication_key=f"safety_proposal.rejected:{proposal.pk}",
    )
