from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_serializer

from apps.assets.models import Asset
from apps.facilities.models import Facility
from apps.maintenance.models import Fault, MaintenanceOrder, MaintenanceTask
from apps.notifications.models import Notification
from apps.notifications.services import notify_user
from apps.security.models import Incident, IncidentAction
from apps.users.models import Role, User

from .permissions import facilities_for_user


def _raise_drf_validation(error):
    details = getattr(error, "message_dict", None) or {
        "non_field_errors": error.messages
    }
    raise serializers.ValidationError(details) from error


class FacilityReadSerializer(serializers.ModelSerializer):
    created_from_project_id = serializers.UUIDField(read_only=True)
    created_by_id = serializers.UUIDField(read_only=True)
    operations_manager_id = serializers.SerializerMethodField()

    class Meta:
        model = Facility
        fields = [
            "id",
            "created_from_project_id",
            "name",
            "type",
            "location",
            "operation_start_date",
            "status",
            "operations_manager_id",
            "created_by_id",
            "created_at",
            "updated_at",
        ]

    def get_operations_manager_id(self, obj):
        assignments = getattr(obj, "active_operations_assignments", None)
        if assignments is None:
            assignments = obj.assignments.filter(
                role_type="operations_manager", is_active=True
            ).order_by("created_at")
        assignment = next(iter(assignments), None)
        return assignment.user_id if assignment else None


class AssetReadSerializer(serializers.ModelSerializer):
    facility_id = serializers.UUIDField(read_only=True)
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    created_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Asset
        fields = [
            "id",
            "facility_id",
            "facility_name",
            "name",
            "asset_type",
            "category",
            "serial_number",
            "manufacturer",
            "model",
            "location_inside_facility",
            "installation_date",
            "operation_date",
            "current_status",
            "health_score",
            "remaining_useful_life",
            "last_maintenance_date",
            "notes",
            "created_by_id",
            "created_at",
            "updated_at",
        ]


class AssetWriteSerializer(serializers.ModelSerializer):
    facility = serializers.PrimaryKeyRelatedField(queryset=Facility.objects.none())

    class Meta:
        model = Asset
        fields = [
            "facility",
            "name",
            "asset_type",
            "category",
            "serial_number",
            "manufacturer",
            "model",
            "location_inside_facility",
            "installation_date",
            "operation_date",
            "health_score",
            "remaining_useful_life",
            "last_maintenance_date",
            "notes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request:
            self.fields["facility"].queryset = facilities_for_user(request.user)

    def validate(self, attrs):
        if self.instance and "facility" in attrs:
            if attrs["facility"].pk != self.instance.facility_id:
                raise serializers.ValidationError(
                    {"facility": "An asset's facility cannot be changed."}
                )
        return attrs

    def create(self, validated_data):
        asset = Asset(created_by=self.context["request"].user, **validated_data)
        try:
            asset.full_clean()
        except DjangoValidationError as exc:
            _raise_drf_validation(exc)
        asset.save()
        return asset

    def update(self, instance, validated_data):
        for field_name, value in validated_data.items():
            setattr(instance, field_name, value)
        try:
            instance.full_clean()
        except DjangoValidationError as exc:
            _raise_drf_validation(exc)
        instance.save()
        return instance


class AssetStatusInputSerializer(serializers.Serializer):
    target_status = serializers.ChoiceField(choices=Asset.Status.choices)


class MaintenanceOrderReadSerializer(serializers.ModelSerializer):
    asset_id = serializers.UUIDField(read_only=True)
    asset_name = serializers.CharField(source="asset.name", read_only=True)
    facility_id = serializers.UUIDField(source="asset.facility_id", read_only=True)
    assigned_to_id = serializers.UUIDField(read_only=True)
    created_by_id = serializers.UUIDField(read_only=True)
    cancelled_by_id = serializers.UUIDField(read_only=True, allow_null=True)
    tasks = serializers.SerializerMethodField()

    class Meta:
        model = MaintenanceOrder
        fields = [
            "id",
            "reference",
            "asset_id",
            "asset_name",
            "facility_id",
            "type",
            "priority",
            "description",
            "reason",
            "assigned_to_id",
            "expected_execution_date",
            "actual_completion_date",
            "execution_notes",
            "cancelled_at",
            "cancelled_by_id",
            "cancellation_reason",
            "status",
            "tasks",
            "created_by_id",
            "created_at",
            "updated_at",
        ]

    def get_tasks(self, obj) -> list[dict]:
        return MaintenanceTaskSerializer(obj.tasks.all(), many=True).data


class MaintenanceTaskSerializer(serializers.ModelSerializer):
    done = serializers.SerializerMethodField()

    class Meta:
        model = MaintenanceTask
        fields = ["id", "sequence", "label", "done", "completed_at", "completed_by_id"]

    def get_done(self, obj) -> bool:
        return obj.completed_at is not None


class MaintenanceOrderWriteSerializer(serializers.ModelSerializer):
    asset = serializers.PrimaryKeyRelatedField(queryset=Asset.objects.none())
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(status=User.STATUS_ACTIVE),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = MaintenanceOrder
        fields = [
            "asset",
            "type",
            "priority",
            "description",
            "reason",
            "assigned_to",
            "expected_execution_date",
            "execution_notes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request:
            self.fields["asset"].queryset = Asset.objects.filter(
                facility__in=facilities_for_user(request.user)
            )
            self.fields["assigned_to"].queryset = User.objects.filter(
                status=User.STATUS_ACTIVE,
                role__name=Role.OPERATIONS_MANAGER,
                facility_assignments__facility__in=facilities_for_user(request.user),
                facility_assignments__is_active=True,
            ).distinct()

    def validate(self, attrs):
        if self.instance and "asset" in attrs:
            if attrs["asset"].pk != self.instance.asset_id:
                raise serializers.ValidationError(
                    {"asset": "A maintenance order's asset cannot be changed."}
                )
        asset = attrs.get("asset", getattr(self.instance, "asset", None))
        assignee = attrs.get("assigned_to", getattr(self.instance, "assigned_to", None))
        if assignee and asset and not assignee.facility_assignments.filter(
            facility=asset.facility,
            is_active=True,
        ).exists():
            raise serializers.ValidationError(
                {"assigned_to": "The assignee must be assigned to the asset facility."}
            )
        return attrs

    def create(self, validated_data):
        if validated_data.get("assigned_to"):
            validated_data["status"] = MaintenanceOrder.Status.ASSIGNED
        order = MaintenanceOrder(
            created_by=self.context["request"].user,
            **validated_data,
        )
        try:
            order.full_clean()
        except DjangoValidationError as exc:
            _raise_drf_validation(exc)
        order.save()
        if order.assigned_to:
            notify_user(
                order.assigned_to,
                title="Maintenance order assigned",
                body=f"{order.reference} has been assigned to you.",
                category=Notification.Category.MAINTENANCE,
                tone=Notification.Tone.INFO,
                href=f"/operations/work-orders/{order.pk}",
                source=order,
            )
        return order

    def update(self, instance, validated_data):
        previous_assignee_id = instance.assigned_to_id
        for field_name, value in validated_data.items():
            setattr(instance, field_name, value)
        if "assigned_to" in validated_data:
            if instance.assigned_to and instance.status == MaintenanceOrder.Status.OPEN:
                instance.status = MaintenanceOrder.Status.ASSIGNED
            elif not instance.assigned_to and instance.status == MaintenanceOrder.Status.ASSIGNED:
                instance.status = MaintenanceOrder.Status.OPEN
        try:
            instance.full_clean()
        except DjangoValidationError as exc:
            _raise_drf_validation(exc)
        instance.save()
        if instance.assigned_to_id and instance.assigned_to_id != previous_assignee_id:
            notify_user(
                instance.assigned_to,
                title="Maintenance order assigned",
                body=f"{instance.reference} has been assigned to you.",
                category=Notification.Category.MAINTENANCE,
                tone=Notification.Tone.INFO,
                href=f"/operations/work-orders/{instance.pk}",
                source=instance,
            )
        return instance


class MaintenanceCompletionInputSerializer(serializers.Serializer):
    actual_completion_date = serializers.DateField()


class MaintenanceCancellationInputSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)


class MaintenanceTaskInputSerializer(serializers.Serializer):
    completed = serializers.BooleanField()


class MaintenanceNotesInputSerializer(serializers.Serializer):
    notes = serializers.CharField(allow_blank=True)


class FaultReadSerializer(serializers.ModelSerializer):
    asset_id = serializers.UUIDField(read_only=True)
    asset_name = serializers.CharField(source="asset.name", read_only=True)
    facility_id = serializers.UUIDField(source="asset.facility_id", read_only=True)
    reported_by_id = serializers.UUIDField(read_only=True)
    assigned_engineer_id = serializers.UUIDField(read_only=True)
    created_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Fault
        fields = [
            "id",
            "asset_id",
            "asset_name",
            "facility_id",
            "fault_type",
            "description",
            "severity",
            "discovery_time",
            "reported_by_id",
            "assigned_engineer_id",
            "root_cause",
            "resolution",
            "resolved_at",
            "status",
            "created_by_id",
            "created_at",
            "updated_at",
        ]


class FaultWriteSerializer(serializers.ModelSerializer):
    asset = serializers.PrimaryKeyRelatedField(queryset=Asset.objects.none())

    class Meta:
        model = Fault
        fields = [
            "asset",
            "fault_type",
            "description",
            "severity",
            "discovery_time",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request:
            self.fields["asset"].queryset = Asset.objects.filter(
                facility__in=facilities_for_user(request.user)
            )

    def validate(self, attrs):
        if self.instance and "asset" in attrs:
            if attrs["asset"].pk != self.instance.asset_id:
                raise serializers.ValidationError(
                    {"asset": "A fault's asset cannot be changed."}
                )
        return attrs

    def create(self, validated_data):
        actor = self.context["request"].user
        fault = Fault(
            reported_by=actor,
            created_by=actor,
            **validated_data,
        )
        try:
            fault.full_clean()
        except DjangoValidationError as exc:
            _raise_drf_validation(exc)
        fault.save()
        return fault

    def update(self, instance, validated_data):
        for field_name, value in validated_data.items():
            setattr(instance, field_name, value)
        try:
            instance.full_clean()
        except DjangoValidationError as exc:
            _raise_drf_validation(exc)
        instance.save()
        return instance


class FaultInvestigationInputSerializer(serializers.Serializer):
    assigned_engineer = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(status=User.STATUS_ACTIVE),
        required=False,
        allow_null=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request:
            self.fields["assigned_engineer"].queryset = User.objects.filter(
                status=User.STATUS_ACTIVE,
                role__name=Role.OPERATIONS_MANAGER,
                facility_assignments__facility__in=facilities_for_user(request.user),
                facility_assignments__is_active=True,
            ).distinct()


class FaultResolutionInputSerializer(serializers.Serializer):
    root_cause = serializers.CharField(allow_blank=False, trim_whitespace=True)
    resolution = serializers.CharField(allow_blank=False, trim_whitespace=True)


@extend_schema_serializer(component_name="OperationsIncidentRead")
class IncidentReadSerializer(serializers.ModelSerializer):
    facility_id = serializers.UUIDField(read_only=True)
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    alert_id = serializers.UUIDField(read_only=True)
    assigned_to_id = serializers.UUIDField(read_only=True)
    closed_by_id = serializers.UUIDField(read_only=True)
    created_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Incident
        fields = [
            "id",
            "incident_number",
            "facility_id",
            "facility_name",
            "alert_id",
            "incident_type",
            "description",
            "location",
            "severity_level",
            "assigned_to_id",
            "status",
            "final_report",
            "closed_by_id",
            "closed_at",
            "created_by_id",
            "created_at",
            "updated_at",
        ]


class IncidentActionReadSerializer(serializers.ModelSerializer):
    incident_id = serializers.UUIDField(read_only=True)
    taken_by_id = serializers.UUIDField(read_only=True)
    created_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = IncidentAction
        fields = [
            "id",
            "incident_id",
            "action_taken",
            "notes",
            "taken_by_id",
            "taken_at",
            "created_by_id",
            "created_at",
        ]
