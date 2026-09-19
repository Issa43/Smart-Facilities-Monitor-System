from datetime import date, timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, OuterRef, Subquery
from django.db.models.functions import TruncMonth
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.construction_manager.permissions import IsConstructionManagerOrSuperAdmin
from api.v1.operations_manager.permissions import IsOperationsManagerOrSuperAdmin, facilities_for_user
from api.v1.security_officer.permissions import IsSecurityOfficerOrSuperAdmin, facilities_for_security_user
from apps.assets.models import Asset
from apps.common.permissions import IsSuperAdmin
from apps.construction.models import QualityInspection
from apps.maintenance.models import Fault, MaintenanceOrder
from apps.materials.models import Material, MaterialRequest
from apps.projects.models import PhaseProgressLog, Project, ProjectPhase
from apps.projects.services import calculate_project_progress
from apps.security.models import Incident, IncidentAction, SecurityAlert
from apps.users.models import User


TONE_BY_STATUS = {
    "planning": "neutral", "not_started": "neutral", "operational": "success",
    "completed": "success", "closed": "success", "in_progress": "info",
    "under_maintenance": "warning", "out_of_service": "critical",
    "low": "neutral", "medium": "info", "high": "warning", "critical": "critical",
}


def _distribution(queryset, field):
    return [
        {
            "label": row[field],
            "value": row["value"],
            "tone": TONE_BY_STATUS.get(row[field], "neutral"),
        }
        for row in queryset.values(field).annotate(value=Count("id")).order_by(field)
        if row["value"]
    ]


def _monthly(queryset, date_field, *, value_field=None):
    values = queryset.annotate(month=TruncMonth(date_field)).values("month")
    values = values.annotate(value=Avg(value_field) if value_field else Count("id")).order_by("month")
    return [
        {"label": row["month"].strftime("%Y-%m"), "value": round(float(row["value"]), 2)}
        for row in values
        if row["month"] is not None and row["value"] is not None
    ]


def _calendar_months_ago_start(months):
    today = timezone.localdate()
    month_index = today.year * 12 + today.month - 1 - months
    return date(month_index // 12, month_index % 12 + 1, 1)


def _projects_for(user):
    queryset = Project.objects.all()
    if not user.is_superuser and user.role.name != "super_admin":
        queryset = queryset.filter(assignments__user=user, assignments__is_active=True)
    return queryset.distinct()


class AnalyticsView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(self.build(request.user))


class AdminAnalyticsView(AnalyticsView):
    permission_classes = [IsSuperAdmin]

    def build(self, user):
        projects = Project.objects.all()
        facilities = facilities_for_user(user)
        assets = Asset.objects.filter(facility__in=facilities)
        orders = MaintenanceOrder.objects.filter(asset__facility__in=facilities)
        incidents = Incident.objects.all()
        alerts = SecurityAlert.objects.all()
        active_order_statuses = [MaintenanceOrder.Status.OPEN, MaintenanceOrder.Status.ASSIGNED, MaintenanceOrder.Status.IN_PROGRESS]
        project_rows = list(projects.prefetch_related("phases"))
        project_progress = [calculate_project_progress(project) for project in project_rows]
        overall_progress = (
            sum(project_progress) / len(project_progress) if project_progress else 0
        )
        active_project_statuses = [Project.Status.PLANNING, Project.Status.IN_PROGRESS]
        progress_since = _calendar_months_ago_start(5)
        return {
            "total_projects": projects.count(),
            "active_projects": projects.filter(status__in=active_project_statuses).count(),
            "delayed_projects": projects.filter(
                status__in=active_project_statuses,
                expected_completion_date__lt=timezone.localdate(),
            ).count(),
            "overall_progress": round(float(overall_progress), 2),
            "operational_facilities": facilities.filter(status="operational").count(),
            "total_assets": assets.count(),
            "asset_health": round(float(assets.aggregate(value=Avg("health_score"))["value"] or 0), 2),
            "open_work_orders": orders.filter(status__in=active_order_statuses).count(),
            "overdue_work_orders": orders.filter(status__in=active_order_statuses, expected_execution_date__lt=timezone.localdate()).count(),
            "open_incidents": incidents.exclude(status=Incident.Status.CLOSED).count(),
            "critical_alerts": alerts.filter(status=SecurityAlert.Status.NEW, severity_level=SecurityAlert.Severity.CRITICAL).count(),
            "active_users": User.objects.filter(status=User.STATUS_ACTIVE).count(),
            "total_users": User.objects.count(),
            "progress_trend": _monthly(
                PhaseProgressLog.objects.filter(created_at__date__gte=progress_since),
                "created_at",
                value_field="progress_percentage",
            ),
            "projects_by_status": _distribution(projects, "status"),
            "assets_by_status": _distribution(assets, "current_status"),
        }


class ConstructionAnalyticsView(AnalyticsView):
    permission_classes = [IsConstructionManagerOrSuperAdmin]

    def build(self, user):
        projects = _projects_for(user)
        phases = ProjectPhase.objects.filter(project__in=projects)
        requests = MaterialRequest.objects.filter(project__in=projects)
        materials = Material.objects.filter(project__in=projects)
        inspections = QualityInspection.objects.filter(project__in=projects)
        today = timezone.localdate()
        quality = inspections.aggregate(value=Avg("score"))["value"]
        return {
            "my_projects": projects.count(),
            "average_progress": round(float(phases.aggregate(value=Avg("current_progress"))["value"] or 0), 2),
            "active_stages": phases.filter(status=ProjectPhase.Status.IN_PROGRESS).count(),
            "stages_under_review": phases.filter(status__in=[ProjectPhase.Status.REJECTED, ProjectPhase.Status.NEEDS_MODIFICATION]).count(),
            "pending_requests": requests.filter(status__in=[MaterialRequest.Status.SUBMITTED, MaterialRequest.Status.REVIEWED]).count(),
            "low_stock_materials": materials.filter(quantity_remaining__lte=F("min_stock_threshold")).count(),
            "quality_score": round(float(quality), 2) if quality is not None else None,
            "failed_inspections": inspections.filter(result=QualityInspection.Result.FAILED).count(),
            "delayed_stages": phases.exclude(status=ProjectPhase.Status.COMPLETED).filter(expected_completion_date__lt=today).count(),
            "progress_trend": _monthly(PhaseProgressLog.objects.filter(phase__project__in=projects), "created_at", value_field="progress_percentage"),
            "stages_by_status": _distribution(phases, "status"),
        }


class OperationsAnalyticsView(AnalyticsView):
    permission_classes = [IsOperationsManagerOrSuperAdmin]

    def build(self, user):
        facilities = facilities_for_user(user)
        assets = Asset.objects.filter(facility__in=facilities)
        orders = MaintenanceOrder.objects.filter(asset__facility__in=facilities)
        faults = Fault.objects.filter(asset__facility__in=facilities)
        open_statuses = [MaintenanceOrder.Status.OPEN, MaintenanceOrder.Status.ASSIGNED, MaintenanceOrder.Status.IN_PROGRESS]
        month_ago = timezone.localdate() - timedelta(days=30)
        return {
            "facilities": facilities.count(),
            "total_assets": assets.count(),
            "asset_health": round(float(assets.aggregate(value=Avg("health_score"))["value"] or 0), 2),
            "operational_assets": assets.filter(current_status=Asset.Status.OPERATIONAL).count(),
            "out_of_service_assets": assets.filter(current_status=Asset.Status.OUT_OF_SERVICE).count(),
            "open_work_orders": orders.filter(status__in=open_statuses).count(),
            "overdue_work_orders": orders.filter(status__in=open_statuses, expected_execution_date__lt=timezone.localdate()).count(),
            "completed_this_month": orders.filter(actual_completion_date__gte=month_ago).count(),
            "open_faults": faults.exclude(status=Fault.Status.CLOSED).count(),
            "critical_faults": faults.exclude(status=Fault.Status.CLOSED).filter(severity=Fault.Severity.CRITICAL).count(),
            "average_uptime": None,
            "maintenance_trend": _monthly(orders.filter(actual_completion_date__isnull=False), "actual_completion_date"),
            "assets_by_status": _distribution(assets, "current_status"),
        }


class SecurityAnalyticsView(AnalyticsView):
    permission_classes = [IsSecurityOfficerOrSuperAdmin]

    def build(self, user):
        facilities = facilities_for_security_user(user)
        alerts = SecurityAlert.objects.filter(facility__in=facilities)
        incidents = Incident.objects.filter(facility__in=facilities)
        # Response duration is calculated from the first recorded response action.
        response_rows = incidents.annotate(
            first_action_at=Subquery(
                IncidentAction.objects.filter(incident_id=OuterRef("pk"))
                .order_by("taken_at")
                .values("taken_at")[:1]
            )
        ).filter(first_action_at__isnull=False)
        response = response_rows.aggregate(
            value=Avg(ExpressionWrapper(F("first_action_at") - F("created_at"), output_field=DurationField()))
        )["value"]
        return {
            "new_alerts": alerts.filter(status=SecurityAlert.Status.NEW).count(),
            "critical_alerts": alerts.filter(status=SecurityAlert.Status.NEW, severity_level=SecurityAlert.Severity.CRITICAL).count(),
            "alerts_today": alerts.filter(created_at__date=timezone.localdate()).count(),
            "false_alarm_rate": round(alerts.filter(is_false_positive=True).count() * 100 / alerts.count(), 2) if alerts.exists() else 0,
            "open_incidents": incidents.exclude(status=Incident.Status.CLOSED).count(),
            "closed_incidents": incidents.filter(status=Incident.Status.CLOSED).count(),
            "incidents_this_month": incidents.filter(created_at__gte=timezone.now() - timedelta(days=30)).count(),
            "average_response_minutes": round(response.total_seconds() / 60, 2) if response else None,
            "alert_trend": _monthly(alerts, "created_at"),
            "alerts_by_type": _distribution(alerts, "alert_type"),
            "incidents_by_severity": _distribution(incidents, "severity_level"),
        }
