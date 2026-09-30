from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.assets.models import Asset
from apps.audit.services import record_audit
from apps.facilities.models import Facility, FacilityAssignment
from apps.maintenance.models import Fault
from apps.notifications.models import Notification
from apps.notifications.services import notify_user, notify_users
from apps.users.models import Role, User

from .models import Camera, Incident, IncidentAction, IncidentNote, SecurityAlert
from .realtime import schedule_security_alert_updated_broadcast


def _safe_alert_audit_state(alert):
    return {
        "status": alert.status,
        "is_false_positive": alert.is_false_positive,
        "reviewed_by_id": str(alert.reviewed_by_id) if alert.reviewed_by_id else None,
        "incident_id": (
            str(alert.incident.pk) if hasattr(alert, "incident") else None
        ),
    }


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


def _create_incident_record(
    *,
    facility,
    actor,
    incident_type,
    description,
    location,
    severity_level,
    assigned_to=None,
    alert=None,
):
    _require_active_actor(actor)
    _validate_assignee(assigned_to)
    errors = {}
    if not facility.is_active:
        errors["facility"] = "The incident facility must be active."
    if not (incident_type or "").strip():
        errors["incident_type"] = "An incident type is required."
    if not (description or "").strip():
        errors["description"] = "An incident description is required."
    if not (location or "").strip():
        errors["location"] = "An incident location is required."
    if severity_level not in Incident.Severity.values:
        errors["severity_level"] = "A valid incident severity is required."
    if errors:
        raise ValidationError(errors)

    incident = Incident(
        facility=facility,
        alert=alert,
        incident_type=incident_type,
        description=description,
        location=location,
        severity_level=severity_level,
        assigned_to=assigned_to,
        status=Incident.Status.OPEN,
        created_by=actor,
    )
    incident.full_clean()
    incident.save()
    recipients = list(
        User.objects.filter(
            role__name=Role.SUPER_ADMIN,
            status=User.STATUS_ACTIVE,
        )
    )
    if assigned_to:
        recipients.append(assigned_to)
    notify_users(
        recipients,
        title="تم تسجيل حادث أمني جديد",
        body=f"الحادث {incident.incident_number} في {incident.facility.name} يتطلب المتابعة.",
        category=Notification.Category.SECURITY,
        tone=(
            Notification.Tone.CRITICAL
            if incident.severity_level == Incident.Severity.CRITICAL
            else Notification.Tone.WARNING
        ),
        href=f"/security/incidents/{incident.pk}",
        source=incident,
        deduplication_key=f"security-incident:{incident.pk}:created",
    )
    return incident


@transaction.atomic
def review_security_alert(*, alert_id, actor, notes="", request=None):
    _require_active_actor(actor)
    alert = _locked_alert(alert_id)
    if alert.status != SecurityAlert.Status.NEW:
        raise ValidationError(
            {"status": "Only a new security alert can be reviewed."}
        )
    if not alert.facility.is_active:
        raise ValidationError({"facility": "The alert facility must be active."})

    before = _safe_alert_audit_state(alert)
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
    record_audit(
        actor=actor,
        action="security_alert.reviewed",
        entity=alert,
        before=before,
        after=_safe_alert_audit_state(alert),
        request=request,
    )
    schedule_security_alert_updated_broadcast(alert.pk)
    return alert


@transaction.atomic
def dismiss_security_alert(*, alert_id, actor, reason, request=None):
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

    before = _safe_alert_audit_state(alert)
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
    record_audit(
        actor=actor,
        action="security_alert.dismissed",
        entity=alert,
        before=before,
        after=_safe_alert_audit_state(alert),
        request=request,
    )
    schedule_security_alert_updated_broadcast(alert.pk)
    return alert


@transaction.atomic
def convert_alert_to_incident(
    *,
    alert_id,
    actor,
    incident_type,
    description,
    assigned_to=None,
    request=None,
):
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

    incident = _create_incident_record(
        facility=alert.facility,
        alert=alert,
        incident_type=incident_type,
        description=description,
        location=alert.location,
        severity_level=alert.severity_level,
        assigned_to=assigned_to,
        actor=actor,
    )

    before = _safe_alert_audit_state(alert)
    alert.status = SecurityAlert.Status.CONVERTED
    alert.full_clean()
    alert.save(update_fields=["status", "updated_at"])
    record_audit(
        actor=actor,
        action="security_alert.converted_to_incident",
        entity=alert,
        before=before,
        after=_safe_alert_audit_state(alert),
        request=request,
    )
    schedule_security_alert_updated_broadcast(alert.pk)
    return incident


@transaction.atomic
def create_manual_incident(
    *,
    facility_id,
    actor,
    incident_type,
    description,
    location,
    severity_level,
    assigned_to=None,
):
    facility = Facility.all_objects.select_for_update(of=("self",)).get(
        pk=facility_id,
        is_active=True,
    )
    return _create_incident_record(
        facility=facility,
        actor=actor,
        incident_type=incident_type,
        description=description,
        location=location,
        severity_level=severity_level,
        assigned_to=assigned_to,
    )


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
    notify_user(
        assigned_to,
        title="Security incident transferred",
        body=f"Incident {incident.incident_number} has been transferred to you.",
        category=Notification.Category.SECURITY,
        tone=Notification.Tone.WARNING,
        href=f"/security/incidents/{incident.pk}",
        source=incident,
    )
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
    if incident.actions.filter(completed_at__isnull=True).exists():
        raise ValidationError(
            {"actions": "All response actions must be completed before closure."}
        )

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


@transaction.atomic
def set_incident_action_completion(*, incident_id, action_id, actor, completed):
    _require_active_actor(actor)
    incident = _locked_incident(incident_id)
    if incident.status == Incident.Status.CLOSED:
        raise ValidationError({"status": "Closed incidents cannot change response actions."})
    action = IncidentAction.all_objects.select_for_update().get(
        pk=action_id,
        incident=incident,
        is_active=True,
    )
    action.completed_at = timezone.now() if completed else None
    action.completed_by = actor if completed else None
    action.full_clean()
    action.save(update_fields=["completed_at", "completed_by", "updated_at"])
    return action


@transaction.atomic
def record_incident_note(*, incident_id, actor, body):
    _require_active_actor(actor, "author")
    if not (body or "").strip():
        raise ValidationError({"body": "An incident note is required."})
    incident = _locked_incident(incident_id)
    if incident.status == Incident.Status.CLOSED:
        raise ValidationError({"status": "Notes cannot be added to a closed incident."})
    note = IncidentNote(incident=incident, author=actor, created_by=actor, body=body.strip())
    note.full_clean(); note.save()
    return note


MAX_REQUIRED_CAMERA_COUNT = 200
CAMERA_MAINTENANCE_FAULT_TYPE = "camera_maintenance"
OPEN_CAMERA_FAULT_STATUSES = (Fault.Status.REPORTED, Fault.Status.INVESTIGATING)


def _camera_code_prefix(facility):
    return f"CAM-{facility.pk.hex[:12].upper()}-"


def _next_camera_number(facility):
    """Next free sequence for the Facility, counting soft-deleted rows too."""
    prefix = _camera_code_prefix(facility)
    identifiers = list(
        Camera.all_objects.filter(code__startswith=prefix).values_list("code", flat=True)
    ) + list(
        Asset.all_objects.filter(serial_number__startswith=prefix).values_list(
            "serial_number", flat=True
        )
    )
    numbers = [
        int(identifier[len(prefix):])
        for identifier in identifiers
        if identifier[len(prefix):].isdigit()
    ]
    return max(numbers, default=0) + 1


def _create_camera_asset(*, facility, serial_number, name, location, actor):
    asset = Asset(
        facility=facility,
        name=name,
        asset_type="camera",
        category="security",
        serial_number=serial_number,
        manufacturer="Unspecified",
        model="Unspecified",
        location_inside_facility=location or "Unassigned",
        installation_date=timezone.localdate(),
        created_by=actor,
    )
    asset.full_clean()
    asset.save()
    return asset


@transaction.atomic
def reconcile_facility_cameras(*, facility_id, required, actor, request=None):
    """Bring a Facility's active Cameras up to an absolute required count.

    Missing Cameras are created, each paired with a camera Asset so the
    existing Fault and MaintenanceOrder workflow can target it. Surplus
    Cameras are only reported: nothing is deleted or deactivated.
    """
    _require_active_actor(actor)
    if (
        isinstance(required, bool)
        or not isinstance(required, int)
        or not 0 <= required <= MAX_REQUIRED_CAMERA_COUNT
    ):
        raise ValidationError(
            {
                "required_camera_count": (
                    f"The required camera count must be between 0 and "
                    f"{MAX_REQUIRED_CAMERA_COUNT}."
                )
            }
        )
    facility = Facility.all_objects.select_for_update().get(
        pk=facility_id,
        is_active=True,
    )
    if facility.status == Facility.Status.DECOMMISSIONED:
        raise ValidationError(
            {"status": "Cameras cannot be provisioned for a decommissioned facility."}
        )

    # Counted only after the Facility row lock, so concurrent requests see
    # each other's Cameras and the absolute target is never exceeded.
    previous_required = facility.required_camera_count
    existing = Camera.objects.filter(facility=facility).count()
    to_create = max(0, required - existing)
    prefix = _camera_code_prefix(facility)
    first_number = _next_camera_number(facility) if to_create else 0
    created = []
    for number in range(first_number, first_number + to_create):
        code = f"{prefix}{number:03d}"
        label = f"Camera {number:03d}"
        asset = _create_camera_asset(
            facility=facility,
            serial_number=code,
            name=label,
            location="Unassigned",
            actor=actor,
        )
        camera = Camera(
            facility=facility,
            asset=asset,
            code=code,
            name=label,
            zone="Unassigned",
            created_by=actor,
        )
        camera.full_clean()
        camera.save()
        created.append(camera)

    if previous_required != required:
        facility.required_camera_count = required
        facility.full_clean()
        facility.save(update_fields=["required_camera_count", "updated_at"])

    surplus = max(0, existing - required)
    if created or previous_required != required:
        record_audit(
            actor=actor,
            action="facility.cameras_reconciled",
            entity=facility,
            before={
                "required_camera_count": previous_required,
                "active_camera_count": existing,
            },
            after={
                "required_camera_count": required,
                "active_camera_count": existing + len(created),
                "created_count": len(created),
                "surplus_count": surplus,
            },
            request=request,
        )
    return {
        "facility": facility,
        "previous_required": previous_required,
        "existing": existing,
        "created": created,
        "surplus": surplus,
    }


@transaction.atomic
def report_camera_maintenance(*, camera_id, actor, description, severity, request=None):
    """Raise (or return the already open) camera-maintenance Fault.

    Returns ``(fault, created)``. The Fault enters the existing Operations
    Manager workflow in the reported state; nothing else is changed here.
    """
    _require_active_actor(actor)
    description = (description or "").strip()
    if not description:
        raise ValidationError({"description": "A maintenance description is required."})
    camera = (
        Camera.all_objects.select_for_update(of=("self",))
        .select_related("facility", "asset")
        .get(pk=camera_id, is_active=True)
    )
    facility = camera.facility
    if actor.role.name != Role.SUPER_ADMIN and not FacilityAssignment.objects.filter(
        facility=facility,
        user=actor,
        is_active=True,
    ).exists():
        raise PermissionDenied("The camera is outside the actor's facility scope.")
    if not facility.is_active:
        raise ValidationError({"facility": "The camera facility must be active."})

    if camera.asset_id is None:
        serial_number = camera.code
        if Asset.all_objects.filter(serial_number=serial_number).exists():
            serial_number = f"CAM-ASSET-{camera.pk.hex[:12].upper()}"
        camera.asset = _create_camera_asset(
            facility=facility,
            serial_number=serial_number,
            name=camera.name,
            location=camera.zone,
            actor=actor,
        )
        camera.full_clean()
        camera.save(update_fields=["asset", "updated_at"])

    open_fault = (
        Fault.objects.filter(
            asset=camera.asset,
            fault_type=CAMERA_MAINTENANCE_FAULT_TYPE,
            status__in=OPEN_CAMERA_FAULT_STATUSES,
        )
        .order_by("created_at")
        .first()
    )
    if open_fault is not None:
        return open_fault, False

    fault = Fault(
        asset=camera.asset,
        fault_type=CAMERA_MAINTENANCE_FAULT_TYPE,
        description=description,
        severity=severity,
        reported_by=actor,
        created_by=actor,
    )
    fault.full_clean()
    fault.save()
    record_audit(
        actor=actor,
        action="camera.maintenance_reported",
        entity=fault,
        after={
            "camera_id": str(camera.pk),
            "camera_code": camera.code,
            "asset_id": str(camera.asset_id),
            "severity": fault.severity,
            "status": fault.status,
        },
        request=request,
    )
    managers = User.objects.filter(
        status=User.STATUS_ACTIVE,
        role__name=Role.OPERATIONS_MANAGER,
        facility_assignments__facility=facility,
        facility_assignments__is_active=True,
    ).distinct()
    notify_users(
        managers,
        title="Camera maintenance reported",
        body=(
            f"{fault.reference}: {camera.name} ({camera.code}) at "
            f"{facility.name} needs maintenance."
        ),
        category=Notification.Category.MAINTENANCE,
        tone=Notification.Tone.WARNING,
        href="/operations/faults",
        source=fault,
        deduplication_key=f"camera-fault:{fault.pk}",
    )
    return fault, True
