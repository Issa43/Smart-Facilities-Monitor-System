from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Prefetch
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.exceptions import DomainConflict
from apps.assets.models import Asset
from apps.assets.services import transition_asset_status
from apps.audit.services import record_audit
from apps.facilities.models import Facility, FacilityAssignment
from apps.maintenance.models import Fault, MaintenanceOrder
from apps.maintenance.services import (
    begin_fault_investigation,
    close_fault,
    close_maintenance_order,
    complete_maintenance_order,
    resolve_fault,
    start_maintenance_order,
    cancel_maintenance_order,
    set_maintenance_execution_notes,
    set_maintenance_task_completion,
)
from apps.security.models import Incident
from apps.users.models import Role, User
from apps.users.serializers import UserSerializer

from .permissions import IsOperationsManagerOrSuperAdmin, facilities_for_user
from .serializers import (
    AssetReadSerializer,
    AssetStatusInputSerializer,
    AssetWriteSerializer,
    FacilityReadSerializer,
    FaultInvestigationInputSerializer,
    FaultReadSerializer,
    FaultResolutionInputSerializer,
    FaultWriteSerializer,
    IncidentActionReadSerializer,
    IncidentReadSerializer,
    MaintenanceCompletionInputSerializer,
    MaintenanceCancellationInputSerializer,
    MaintenanceNotesInputSerializer,
    MaintenanceTaskInputSerializer,
    MaintenanceTaskSerializer,
    MaintenanceOrderReadSerializer,
    MaintenanceOrderWriteSerializer,
)


def _domain_conflict(error):
    details = getattr(error, "message_dict", None) or {
        "non_field_errors": error.messages
    }
    return DomainConflict(detail=details)


class ScopedOperationsMixin:
    permission_classes = [IsOperationsManagerOrSuperAdmin]
    lookup_value_regex = (
        "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    )

    def visible_facilities(self):
        return facilities_for_user(self.request.user)


class FacilityViewSet(ScopedOperationsMixin, viewsets.ReadOnlyModelViewSet):
    permission_required = "asset.manage"
    serializer_class = FacilityReadSerializer
    filterset_fields = ["status", "type"]
    search_fields = ["name", "location"]
    ordering_fields = ["name", "type", "status", "created_at", "updated_at"]
    ordering = ["name"]

    def get_queryset(self):
        return self.visible_facilities().select_related(
            "created_from_project", "created_by"
        ).annotate(asset_count=Count("assets", distinct=True)).prefetch_related(
            Prefetch(
                "assignments",
                queryset=FacilityAssignment.objects.filter(
                    role_type=FacilityAssignment.RoleType.OPERATIONS_MANAGER,
                    is_active=True,
                ).order_by("created_at"),
                to_attr="active_operations_assignments",
            )
        )

    @action(detail=True, methods=["get"], url_path="monitoring")
    def monitoring(self, request, pk=None):
        facility = self.get_object()
        assets = Asset.objects.filter(facility=facility)
        orders = MaintenanceOrder.objects.filter(asset__facility=facility)
        faults = Fault.objects.filter(asset__facility=facility)
        incidents = Incident.objects.filter(facility=facility)
        return Response(
            {
                "facility": FacilityReadSerializer(facility).data,
                "asset_count": assets.count(),
                "asset_status_counts": {
                    value: assets.filter(current_status=value).count()
                    for value in Asset.Status.values
                },
                "active_maintenance_orders": orders.exclude(
                    status__in=[MaintenanceOrder.Status.CLOSED, MaintenanceOrder.Status.CANCELLED]
                ).count(),
                "open_faults": faults.exclude(status=Fault.Status.CLOSED).count(),
                "open_incidents": incidents.exclude(
                    status=Incident.Status.CLOSED
                ).count(),
            }
        )


class AssetViewSet(
    ScopedOperationsMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    permission_required = {
        "transition_status": "asset.status",
        "default": "asset.manage",
    }
    filterset_fields = [
        "facility",
        "current_status",
        "asset_type",
        "category",
        "manufacturer",
        "location_inside_facility",
    ]
    search_fields = [
        "name",
        "asset_type",
        "category",
        "serial_number",
        "manufacturer",
        "model",
        "location_inside_facility",
    ]
    ordering_fields = [
        "name",
        "asset_type",
        "category",
        "manufacturer",
        "health_score",
        "installation_date",
        "created_at",
        "updated_at",
    ]
    ordering = ["name"]

    def get_queryset(self):
        return Asset.objects.filter(
            facility__in=self.visible_facilities()
        ).select_related("facility", "created_by")

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return AssetWriteSerializer
        return AssetReadSerializer

    @staticmethod
    def _audit_snapshot(asset):
        return {
            "name": asset.name,
            "asset_type": asset.asset_type,
            "category": asset.category,
            "serial_number": asset.serial_number,
            "manufacturer": asset.manufacturer,
            "model": asset.model,
            "location_inside_facility": asset.location_inside_facility,
            "installation_date": asset.installation_date.isoformat(),
            "operation_date": (
                asset.operation_date.isoformat() if asset.operation_date else None
            ),
            "current_status": asset.current_status,
            "facility_id": str(asset.facility_id),
            "is_active": asset.is_active,
        }

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                asset = serializer.save()
                record_audit(
                    actor=request.user,
                    action="asset.created",
                    entity=asset,
                    after=self._audit_snapshot(asset),
                    request=request,
                )
        except IntegrityError as exc:
            raise DomainConflict("An asset with this identity already exists.") from exc
        return Response(AssetReadSerializer(asset).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        asset = self.get_object()
        before = self._audit_snapshot(asset)
        serializer = self.get_serializer(asset, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                asset = serializer.save()
                record_audit(
                    actor=request.user,
                    action="asset.updated",
                    entity=asset,
                    before=before,
                    after=self._audit_snapshot(asset),
                    request=request,
                )
        except IntegrityError as exc:
            raise DomainConflict("An asset with this identity already exists.") from exc
        return Response(AssetReadSerializer(asset).data)

    def destroy(self, request, *args, **kwargs):
        asset = self.get_object()
        if asset.maintenance_orders.exists() or asset.faults.exists():
            raise DomainConflict("Assets with operational history cannot be archived.")
        before = self._audit_snapshot(asset)
        with transaction.atomic():
            asset.soft_delete()
            record_audit(
                actor=request.user,
                action="asset.archived",
                entity=asset,
                before=before,
                after=self._audit_snapshot(asset),
                request=request,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], url_path="filter-options")
    def filter_options(self, request):
        """Return real, scoped filter values without inventing lookup tables."""
        assets = self.get_queryset()

        def distinct_values(field):
            return list(
                assets.exclude(**{field: ""})
                .order_by(field)
                .values_list(field, flat=True)
                .distinct()
            )

        return Response(
            {
                "asset_types": distinct_values("asset_type"),
                "categories": distinct_values("category"),
                "manufacturers": distinct_values("manufacturer"),
            }
        )

    @action(detail=False, methods=["get"], url_path="monitoring")
    def monitoring(self, request):
        assets = self.filter_queryset(self.get_queryset())
        aggregates = assets.aggregate(
            total=Count("id"),
            average_health_score=Avg("health_score"),
        )
        return Response(
            {
                **aggregates,
                "status_counts": {
                    value: assets.filter(current_status=value).count()
                    for value in Asset.Status.values
                },
            }
        )

    @action(detail=True, methods=["post"], url_path="transition-status")
    def transition_status(self, request, pk=None):
        asset = self.get_object()
        before = self._audit_snapshot(asset)
        payload = AssetStatusInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            asset = transition_asset_status(
                asset_id=asset.id,
                target_status=payload.validated_data["target_status"],
            )
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        record_audit(
            actor=request.user,
            action="asset.status_transitioned",
            entity=asset,
            before=before,
            after=self._audit_snapshot(asset),
            request=request,
        )
        return Response(AssetReadSerializer(asset).data)


class MaintenanceOrderViewSet(
    ScopedOperationsMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    permission_required = {
        "create": "workorder.create",
        "close": "workorder.close",
        "default": "workorder.create",
    }
    filterset_fields = ["asset", "asset__facility", "type", "priority", "status"]
    search_fields = ["asset__name", "description", "reason"]
    ordering_fields = ["expected_execution_date", "priority", "created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return MaintenanceOrder.objects.filter(
            asset__facility__in=self.visible_facilities()
        ).select_related(
            "asset", "asset__facility", "assigned_to", "created_by"
        ).prefetch_related("tasks")

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return MaintenanceOrderWriteSerializer
        return MaintenanceOrderReadSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(
            MaintenanceOrderReadSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        order = self.get_object()
        serializer = self.get_serializer(order, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(MaintenanceOrderReadSerializer(order).data)

    def _transition(self, service, **service_kwargs):
        order = self.get_object()
        try:
            order = service(order_id=order.id, **service_kwargs)
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(MaintenanceOrderReadSerializer(order).data)

    @action(detail=True, methods=["post"], url_path="start")
    def start(self, request, pk=None):
        return self._transition(start_maintenance_order)

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        payload = MaintenanceCompletionInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self._transition(
            complete_maintenance_order,
            actual_completion_date=payload.validated_data["actual_completion_date"],
        )

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        return self._transition(close_maintenance_order)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        payload = MaintenanceCancellationInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self._transition(cancel_maintenance_order, actor=request.user, reason=payload.validated_data["reason"])

    @action(detail=True, methods=["patch"], url_path="notes")
    def notes(self, request, pk=None):
        payload = MaintenanceNotesInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self._transition(set_maintenance_execution_notes, notes=payload.validated_data["notes"])

    @action(detail=True, methods=["patch"], url_path=r"tasks/(?P<task_id>[0-9a-fA-F-]{36})")
    def task(self, request, pk=None, task_id=None):
        order = self.get_object()
        payload = MaintenanceTaskInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            task = set_maintenance_task_completion(order_id=order.pk, task_id=task_id, actor=request.user, completed=payload.validated_data["completed"])
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(MaintenanceTaskSerializer(task).data)


class FaultViewSet(
    ScopedOperationsMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    permission_required = "fault.manage"
    filterset_fields = ["asset", "asset__facility", "severity", "status"]
    search_fields = ["asset__name", "fault_type", "description"]
    ordering_fields = ["discovery_time", "severity", "created_at"]
    ordering = ["-discovery_time"]

    def get_queryset(self):
        return Fault.objects.filter(
            asset__facility__in=self.visible_facilities()
        ).select_related(
            "asset",
            "asset__facility",
            "reported_by",
            "assigned_engineer",
            "created_by",
        )

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return FaultWriteSerializer
        return FaultReadSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fault = serializer.save()
        return Response(FaultReadSerializer(fault).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        fault = self.get_object()
        serializer = self.get_serializer(fault, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        fault = serializer.save()
        return Response(FaultReadSerializer(fault).data)

    def _transition(self, service, **service_kwargs):
        fault = self.get_object()
        try:
            fault = service(fault_id=fault.id, **service_kwargs)
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(FaultReadSerializer(fault).data)

    @action(detail=True, methods=["post"], url_path="investigate")
    def investigate(self, request, pk=None):
        payload = FaultInvestigationInputSerializer(
            data=request.data,
            context={"request": request},
        )
        payload.is_valid(raise_exception=True)
        assigned_engineer = payload.validated_data.get("assigned_engineer")
        if assigned_engineer and not assigned_engineer.facility_assignments.filter(
            facility=self.get_object().asset.facility,
            is_active=True,
        ).exists():
            raise ValidationError(
                {"assigned_engineer": "The engineer must be assigned to this facility."}
            )
        return self._transition(
            begin_fault_investigation,
            assigned_engineer=assigned_engineer,
        )

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve(self, request, pk=None):
        payload = FaultResolutionInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self._transition(resolve_fault, **payload.validated_data)

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        return self._transition(close_fault)


class OperationalIncidentViewSet(ScopedOperationsMixin, viewsets.ReadOnlyModelViewSet):
    permission_required = "incident.update"
    serializer_class = IncidentReadSerializer
    filterset_fields = ["facility", "status", "severity_level", "incident_type"]
    search_fields = ["incident_number", "incident_type", "description", "location"]
    ordering_fields = ["severity_level", "closed_at", "created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return Incident.objects.filter(
            facility__in=self.visible_facilities()
        ).select_related(
            "facility", "alert", "assigned_to", "closed_by", "created_by"
        )

    @action(detail=True, methods=["get"], url_path="actions")
    def actions(self, request, pk=None):
        incident = self.get_object()
        queryset = incident.actions.select_related("taken_by", "created_by").order_by(
            "-taken_at"
        )
        page = self.paginate_queryset(queryset)
        serializer = IncidentActionReadSerializer(
            page if page is not None else queryset,
            many=True,
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class OperationsMonitoringView(APIView):
    permission_required = "asset.manage"
    permission_classes = [IsOperationsManagerOrSuperAdmin]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        facilities = facilities_for_user(request.user)
        assets = Asset.objects.filter(facility__in=facilities)
        orders = MaintenanceOrder.objects.filter(asset__facility__in=facilities)
        faults = Fault.objects.filter(asset__facility__in=facilities)
        incidents = Incident.objects.filter(facility__in=facilities)
        return Response(
            {
                "facility_count": facilities.count(),
                "asset_count": assets.count(),
                "active_maintenance_orders": orders.exclude(
                    status__in=[MaintenanceOrder.Status.CLOSED, MaintenanceOrder.Status.CANCELLED]
                ).count(),
                "open_faults": faults.exclude(status=Fault.Status.CLOSED).count(),
                "open_incidents": incidents.exclude(
                    status=Incident.Status.CLOSED
                ).count(),
            }
        )


class OperationsAssigneeView(APIView):
    permission_required = "workorder.create"
    permission_classes = [IsOperationsManagerOrSuperAdmin]

    @extend_schema(responses=UserSerializer(many=True))
    def get(self, request):
        users = User.objects.filter(status=User.STATUS_ACTIVE, role__name=Role.OPERATIONS_MANAGER)
        if request.user.role.name != Role.SUPER_ADMIN:
            users = users.filter(facility_assignments__facility__in=facilities_for_user(request.user), facility_assignments__is_active=True)
        users = users.select_related("role").distinct().order_by("full_name")
        return Response(UserSerializer(users, many=True).data)
