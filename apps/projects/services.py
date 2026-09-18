from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Avg
from django.utils import timezone

from apps.facilities.models import Facility
from apps.materials.models import MaterialRequest
from apps.notifications.models import Notification
from apps.notifications.services import notify_users
from apps.notifications.services import setting_enabled

from .models import (
    PhaseProgressLog,
    PhaseReviewLog,
    Project,
    ProjectAssignment,
    ProjectPhase,
)


BLOCKING_MATERIAL_REQUEST_STATUSES = (
    MaterialRequest.Status.SUBMITTED,
    MaterialRequest.Status.REVIEWED,
    MaterialRequest.Status.APPROVED,
)


def _require_actor(actor):
    if actor is None or not getattr(actor, "pk", None):
        raise ValidationError({"actor": "An authenticated actor is required."})
    if not actor.is_active:
        raise ValidationError({"actor": "The actor must be active."})


def _as_progress(value):
    try:
        progress = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({"progress_percentage": "Valid progress is required."}) from exc

    if not progress.is_finite() or progress < 0 or progress > 100:
        raise ValidationError(
            {"progress_percentage": "Progress must be between 0 and 100."}
        )
    if progress.as_tuple().exponent < -2:
        raise ValidationError(
            {"progress_percentage": "Progress cannot exceed two decimal places."}
        )
    return progress


def calculate_project_progress(project):
    prefetched_phases = getattr(project, "_prefetched_objects_cache", {}).get(
        "phases"
    )
    if prefetched_phases is not None:
        values = [phase.current_progress for phase in prefetched_phases]
        if not values:
            return Decimal("0.00")
        average = sum(values, Decimal("0.00")) / len(values)
        return average.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    average = ProjectPhase.objects.filter(project=project).aggregate(
        value=Avg("current_progress")
    )["value"]
    if average is None:
        return Decimal("0.00")
    return average.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validate_project_completion(project):
    phases = ProjectPhase.objects.filter(project=project)
    if not phases.exists():
        raise ValidationError({"phases": "A project requires active phases."})

    rejected = phases.filter(status=ProjectPhase.Status.REJECTED)
    if rejected.exists():
        raise ValidationError(
            {"phases": "Rejected phases block project completion."}
        )

    incomplete = phases.exclude(status=ProjectPhase.Status.COMPLETED)
    if incomplete.exists():
        raise ValidationError(
            {"phases": "All active phases must be completed first."}
        )

    blocking_requests = MaterialRequest.objects.filter(
        project=project,
        status__in=BLOCKING_MATERIAL_REQUEST_STATUSES,
    )
    if blocking_requests.exists():
        raise ValidationError(
            {"material_requests": "Blocking material requests must be resolved first."}
        )


@transaction.atomic
def start_project(*, project_id):
    project = Project.all_objects.select_for_update().get(
        pk=project_id,
        is_active=True,
    )
    if project.status != Project.Status.PLANNING:
        raise ValidationError(
            {"status": "Only a planning project can be started."}
        )
    if not ProjectPhase.objects.filter(project=project).exists():
        raise ValidationError({"phases": "A project requires active phases."})
    if not ProjectAssignment.objects.filter(
        project=project,
        role_type=ProjectAssignment.RoleType.PRIMARY_MANAGER,
        user__status="active",
    ).exists():
        raise ValidationError(
            {"assignments": "An active primary manager is required."}
        )

    project.status = Project.Status.IN_PROGRESS
    project.full_clean()
    project.save(update_fields=["status", "updated_at"])
    return project


@transaction.atomic
def complete_project(*, project_id, actual_completion_date):
    project = Project.all_objects.select_for_update().get(
        pk=project_id,
        is_active=True,
    )
    if project.status != Project.Status.IN_PROGRESS:
        raise ValidationError(
            {"status": "Only an in-progress project can be completed."}
        )
    if not isinstance(actual_completion_date, date):
        raise ValidationError(
            {"actual_completion_date": "A valid completion date is required."}
        )

    list(
        ProjectPhase.objects.select_for_update()
        .filter(project=project)
        .values_list("pk", flat=True)
    )
    list(
        MaterialRequest.objects.select_for_update()
        .filter(project=project)
        .values_list("pk", flat=True)
    )
    if setting_enabled("workflow.blockCompletion"):
        validate_project_completion(project)

    project.actual_completion_date = actual_completion_date
    project.status = Project.Status.COMPLETED
    project.full_clean()
    project.save(
        update_fields=["actual_completion_date", "status", "updated_at"]
    )
    return project


@transaction.atomic
def convert_project_to_facility(*, project_id, actor):
    _require_actor(actor)
    project = Project.all_objects.select_for_update().get(
        pk=project_id,
        is_active=True,
    )
    if project.status != Project.Status.COMPLETED:
        raise ValidationError(
            {"status": "Only a completed project can be converted."}
        )
    if Facility.all_objects.select_for_update().filter(
        created_from_project=project
    ).exists():
        raise ValidationError(
            {"project": "This project has already been converted to a facility."}
        )

    facility = Facility(
        created_from_project=project,
        name=project.name,
        type=project.facility_type,
        location=project.location,
        status=Facility.Status.OPERATIONAL,
        created_by=actor,
    )
    facility.full_clean()
    facility.save()
    project.facility = facility
    project.status = Project.Status.OPERATIONAL
    project.full_clean()
    project.save(update_fields=["facility", "status", "updated_at"])
    return facility


@transaction.atomic
def record_phase_progress(
    *,
    phase_id,
    progress_percentage,
    work_completed,
    actor,
    notes="",
):
    _require_actor(actor)
    progress = _as_progress(progress_percentage)
    phase = (
        ProjectPhase.all_objects.select_for_update()
        .select_related("project")
        .get(pk=phase_id, is_active=True)
    )
    if not phase.project.is_active:
        raise ValidationError({"phase": "The phase project must be active."})
    if phase.project.status != Project.Status.IN_PROGRESS:
        raise ValidationError(
            {"project": "Progress can only be recorded for an in-progress project."}
        )
    if phase.status in {ProjectPhase.Status.COMPLETED, ProjectPhase.Status.REJECTED}:
        raise ValidationError(
            {"status": "Completed or finally rejected phases cannot record progress."}
        )
    if progress < phase.current_progress:
        raise ValidationError(
            {"progress_percentage": "Phase progress cannot decrease."}
        )
    if not (work_completed or "").strip():
        raise ValidationError({"work_completed": "Completed work is required."})

    phase.current_progress = progress
    approval_required = setting_enabled("workflow.requireApproval")
    phase.status = (
        ProjectPhase.Status.IN_PROGRESS
        if approval_required or progress != Decimal("100.00")
        else ProjectPhase.Status.COMPLETED
    )
    if phase.actual_start_date is None:
        phase.actual_start_date = timezone.localdate()
    if phase.status == ProjectPhase.Status.COMPLETED:
        phase.actual_completion_date = timezone.localdate()
        phase.approved_by = actor
    phase.full_clean()
    phase.save(
        update_fields=[
            "current_progress",
            "status",
            "actual_start_date",
            "actual_completion_date",
            "approved_by",
            "updated_at",
        ]
    )

    progress_log = PhaseProgressLog(
        phase=phase,
        progress_percentage=progress,
        work_completed=work_completed,
        notes=notes,
        created_by=actor,
    )
    progress_log.full_clean()
    progress_log.save()
    return progress_log


def _review_phase(*, phase_id, actor, decision, disposition=None, reason=""):
    _require_actor(actor)
    phase = (
        ProjectPhase.all_objects.select_for_update()
        .select_related("project")
        .get(pk=phase_id, is_active=True)
    )
    if not phase.project.is_active:
        raise ValidationError({"phase": "The phase project must be active."})
    if phase.project.status != Project.Status.IN_PROGRESS:
        raise ValidationError(
            {"project": "Phases can only be reviewed for an in-progress project."}
        )
    if phase.status not in {
        ProjectPhase.Status.IN_PROGRESS,
        ProjectPhase.Status.NEEDS_MODIFICATION,
    }:
        raise ValidationError({"status": "This phase is not available for review."})

    if decision == PhaseReviewLog.Decision.APPROVED:
        if phase.current_progress != Decimal("100.00"):
            raise ValidationError(
                {"current_progress": "Only a phase at 100% can be approved."}
            )
        phase.status = ProjectPhase.Status.COMPLETED
        phase.approved_by = actor
        phase.approved_at = timezone.now()
        if phase.actual_start_date is None:
            phase.actual_start_date = timezone.localdate()
        if phase.actual_completion_date is None:
            phase.actual_completion_date = timezone.localdate()
    else:
        if not (reason or "").strip():
            raise ValidationError({"reason": "A rejection reason is required."})
        phase.status = (
            ProjectPhase.Status.NEEDS_MODIFICATION
            if disposition == PhaseReviewLog.Disposition.NEEDS_MODIFICATION
            else ProjectPhase.Status.REJECTED
        )
        phase.approved_by = None
        phase.approved_at = None

    phase.full_clean()
    phase.save(
        update_fields=[
            "status",
            "approved_by",
            "approved_at",
            "actual_start_date",
            "actual_completion_date",
            "updated_at",
        ]
    )

    review = PhaseReviewLog(
        phase=phase,
        decision=decision,
        disposition=disposition,
        reason=reason,
        created_by=actor,
    )
    review.full_clean()
    review.save()
    recipients = [
        assignment.user
        for assignment in ProjectAssignment.objects.filter(
            project=phase.project,
            is_active=True,
            user__status="active",
        ).select_related("user")
        if assignment.user_id != actor.pk
    ]
    notify_users(
        recipients,
        title="Construction phase reviewed",
        body=f"{phase.name} is now {phase.get_status_display()}.",
        category=Notification.Category.PROJECT,
        tone=(
            Notification.Tone.SUCCESS
            if decision == PhaseReviewLog.Decision.APPROVED
            else Notification.Tone.WARNING
        ),
        href=f"/construction/stages/{phase.pk}",
        source=phase,
        preference_field="stage_review",
        system_setting_key="notify.stageReview",
    )
    return review


@transaction.atomic
def approve_phase(*, phase_id, actor):
    return _review_phase(
        phase_id=phase_id,
        actor=actor,
        decision=PhaseReviewLog.Decision.APPROVED,
    )


@transaction.atomic
def reject_phase(*, phase_id, actor, reason):
    return _review_phase(
        phase_id=phase_id,
        actor=actor,
        decision=PhaseReviewLog.Decision.REJECTED,
        disposition=PhaseReviewLog.Disposition.FINAL_REJECTION,
        reason=reason,
    )


@transaction.atomic
def request_phase_modification(*, phase_id, actor, reason):
    return _review_phase(
        phase_id=phase_id,
        actor=actor,
        decision=PhaseReviewLog.Decision.REJECTED,
        disposition=PhaseReviewLog.Disposition.NEEDS_MODIFICATION,
        reason=reason,
    )
