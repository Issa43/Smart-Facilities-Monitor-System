from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Incident, IncidentAction, SecurityAlert


def _require_active_actor(actor, field_name="actor"):
    if actor is None or not getattr(actor, "pk", None):
        raise ValidationError({field_name: "An authenticated actor is required."})
    if not actor.is_active:
        raise ValidationError({field_name: "The actor must be active."})


def _validate_assignee(assigned_to):
    if assigned_to is None:
        return
    if not getattr(assigned_to, "pk", None) or not assigned_to.is_active:
        raise ValidationError({"assigned_to": "The assignee must be active."})


def _locked_alert(alert_id):
    return (
        SecurityAlert.all_objects.select_for_update(of=("self",))
        .select_related("facility", "reviewed_by")
        .get(pk=alert_id, is_active=True)
    )


def _locked_incident(incident_id):
    return (
        Incident.all_objects.select_for_update(of=("self",))
        .select_related("facility", "alert", "assigned_to")
        .get(pk=incident_id, is_active=True)
    )


@transaction.atomic
def review_security_alert(*, alert_id, actor, notes=""):
    _require_active_actor(actor)
    alert = _locked_alert(alert_id)
    if alert.status != SecurityAlert.Status.NEW:
        raise ValidationError(
            {"status": "Only a new security alert can be reviewed."}
        )
    if not alert.facility.is_active:
        raise ValidationError({"facility": "The alert facility must be active."})

    alert.status = SecurityAlert.Status.REVIEWED
    alert.reviewed_by = actor
    alert.review_notes = notes or ""
    alert.is_false_positive = False
    alert.full_clean()
    alert.save(
        update_fields=[
            "status",
            "reviewed_by",
            "review_notes",
            "is_false_positive",
            "updated_at",
        ]
    )
    return alert


@transaction.atomic
def dismiss_security_alert(*, alert_id, actor, reason):
    _require_active_actor(actor)
    if not (reason or "").strip():
        raise ValidationError({"reason": "A dismissal reason is required."})

    alert = _locked_alert(alert_id)
    if alert.status != SecurityAlert.Status.REVIEWED:
        raise ValidationError(
            {"status": "Only a reviewed security alert can be dismissed."}
        )
    if not alert.facility.is_active:
        raise ValidationError({"facility": "The alert facility must be active."})

    alert.status = SecurityAlert.Status.DISMISSED
    alert.is_false_positive = True
    alert.reviewed_by = actor
    alert.review_notes = reason
    alert.full_clean()
    alert.save(
        update_fields=[
            "status",
            "is_false_positive",
            "reviewed_by",
            "review_notes",
            "updated_at",
        ]
    )
    return alert


@transaction.atomic
def convert_alert_to_incident(
    *,
    alert_id,
    actor,
    incident_type,
    description,
    assigned_to=None,
):
    _require_active_actor(actor)
    _validate_assignee(assigned_to)
    if not (incident_type or "").strip():
        raise ValidationError({"incident_type": "An incident type is required."})
    if not (description or "").strip():
        raise ValidationError({"description": "An incident description is required."})

    alert = _locked_alert(alert_id)
    if alert.status != SecurityAlert.Status.REVIEWED:
        raise ValidationError(
            {"status": "Only a reviewed security alert can become an incident."}
        )
    if alert.is_false_positive:
        raise ValidationError(
            {"alert": "A false-positive alert cannot become an incident."}
        )
    if not alert.facility.is_active:
        raise ValidationError({"facility": "The alert facility must be active."})
    if Incident.all_objects.select_for_update().filter(alert=alert).exists():
        raise ValidationError(
            {"alert": "This security alert already has an incident."}
        )

    incident = Incident(
        facility=alert.facility,
        alert=alert,
        incident_type=incident_type,
        description=description,
        location=alert.location,
        severity_level=alert.severity_level,
        assigned_to=assigned_to,
        status=Incident.Status.OPEN,
        created_by=actor,
    )
    incident.full_clean()
    incident.save()

    alert.status = SecurityAlert.Status.CONVERTED
    alert.full_clean()
    alert.save(update_fields=["status", "updated_at"])
    return incident


@transaction.atomic
def start_incident_investigation(*, incident_id, assigned_to=None):
    _validate_assignee(assigned_to)
    incident = _locked_incident(incident_id)
    if incident.status != Incident.Status.OPEN:
        raise ValidationError(
            {"status": "Only an open incident can enter investigation."}
        )
    if not incident.facility.is_active:
        raise ValidationError({"facility": "The incident facility must be active."})

    update_fields = ["status", "updated_at"]
    incident.status = Incident.Status.INVESTIGATION
    if assigned_to is not None:
        incident.assigned_to = assigned_to
        update_fields.append("assigned_to")
    incident.full_clean()
    incident.save(update_fields=update_fields)
    return incident


@transaction.atomic
def transfer_incident(*, incident_id, assigned_to):
    _validate_assignee(assigned_to)
    if assigned_to is None:
        raise ValidationError({"assigned_to": "A transfer assignee is required."})

    incident = _locked_incident(incident_id)
    if incident.status != Incident.Status.INVESTIGATION:
        raise ValidationError(
            {"status": "Only an incident under investigation can be transferred."}
        )
    if not incident.facility.is_active:
        raise ValidationError({"facility": "The incident facility must be active."})

    incident.assigned_to = assigned_to
    incident.status = Incident.Status.TRANSFERRED
    incident.full_clean()
    incident.save(update_fields=["assigned_to", "status", "updated_at"])
    return incident


@transaction.atomic
def close_incident(*, incident_id, actor, final_report):
    _require_active_actor(actor, "closed_by")
    if not (final_report or "").strip():
        raise ValidationError({"final_report": "A final report is required."})

    incident = _locked_incident(incident_id)
    if incident.status not in {
        Incident.Status.INVESTIGATION,
        Incident.Status.TRANSFERRED,
    }:
        raise ValidationError(
            {"status": "Only an investigated or transferred incident can be closed."}
        )
    if not incident.facility.is_active:
        raise ValidationError({"facility": "The incident facility must be active."})

    incident.final_report = final_report
    incident.closed_by = actor
    incident.closed_at = timezone.now()
    incident.status = Incident.Status.CLOSED
    incident.full_clean()
    incident.save(
        update_fields=[
            "final_report",
            "closed_by",
            "closed_at",
            "status",
            "updated_at",
        ]
    )
    return incident


@transaction.atomic
def record_incident_action(*, incident_id, actor, action_taken, notes=""):
    _require_active_actor(actor, "taken_by")
    if not (action_taken or "").strip():
        raise ValidationError({"action_taken": "An incident action is required."})

    incident = _locked_incident(incident_id)
    if incident.status == Incident.Status.CLOSED:
        raise ValidationError(
            {"status": "Actions cannot be added to a closed incident."}
        )
    if not incident.facility.is_active:
        raise ValidationError({"facility": "The incident facility must be active."})

    action = IncidentAction(
        incident=incident,
        action_taken=action_taken,
        notes=notes or "",
        taken_by=actor,
        created_by=actor,
    )
    action.full_clean()
    action.save()
    return action
