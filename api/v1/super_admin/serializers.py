from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from apps.facilities.models import Facility
from apps.projects.models import Project, ProjectAssignment, ProjectPhase
from apps.projects.services import calculate_project_progress
from apps.security.models import (
    AIIngestionCameraScope,
    AIIngestionCredential,
    Camera,
)
from apps.users.models import Role, User


def _raise_drf_validation(error):
    details = getattr(error, "message_dict", None) or {
        "non_field_errors": error.messages
    }
    raise serializers.ValidationError(details) from error


class AIIngestionCameraScopeSerializer(serializers.ModelSerializer):
    camera_id = serializers.UUIDField(read_only=True)
    camera_code = serializers.CharField(source="camera.code", read_only=True)
    camera_name = serializers.CharField(source="camera.name", read_only=True)
    facility_id = serializers.UUIDField(source="camera.facility_id", read_only=True)

    class Meta:
        model = AIIngestionCameraScope
        fields = [
            "id",
            "camera_id",
            "camera_code",
            "camera_name",
            "facility_id",
            "is_active",
            "created_at",
            "updated_at",
        ]


class AIIngestionCredentialReadSerializer(serializers.ModelSerializer):
    principal_id = serializers.UUIDField(read_only=True)
    status = serializers.SerializerMethodField()
    camera_scopes = serializers.SerializerMethodField()

    class Meta:
        model = AIIngestionCredential
        fields = [
            "id",
            "name",
            "key_id",
            "principal_id",
            "status",
            "is_active",
            "expires_at",
            "last_used_at",
            "revoked_at",
            "created_at",
            "updated_at",
            "camera_scopes",
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_status(self, credential):
        if credential.revoked_at:
            return "revoked"
        if credential.is_expired:
            return "expired"
        return "active" if credential.is_active else "inactive"

    @extend_schema_field(AIIngestionCameraScopeSerializer(many=True))
    def get_camera_scopes(self, credential):
        scopes = AIIngestionCameraScope.all_objects.filter(
            credential=credential
        ).select_related("camera__facility")
        return AIIngestionCameraScopeSerializer(scopes, many=True).data


class AIIngestionCredentialCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, allow_blank=False)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    camera_ids = serializers.PrimaryKeyRelatedField(
        source="cameras",
        queryset=Camera.objects.select_related("facility"),
        many=True,
        required=False,
    )

    def validate_expires_at(self, value):
        from django.utils import timezone

        if value and value <= timezone.now():
            raise serializers.ValidationError("Expiration must be in the future.")
        return value


class AIIngestionCameraScopeInputSerializer(serializers.Serializer):
    camera_id = serializers.PrimaryKeyRelatedField(
        source="camera",
        queryset=Camera.objects.select_related("facility"),
    )


class ProjectReadSerializer(serializers.ModelSerializer):
    facility_id = serializers.UUIDField(read_only=True)
    created_by_id = serializers.UUIDField(read_only=True)
    progress_percentage = serializers.SerializerMethodField()
    image_available = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    primary_manager_id = serializers.SerializerMethodField()
    primary_manager_name = serializers.SerializerMethodField()
    current_phase_name = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id",
            "name",
            "facility_id",
            "facility_type",
            "description",
            "location",
            "latitude",
            "longitude",
            "image_available",
            "start_date",
            "expected_completion_date",
            "actual_completion_date",
            "status",
            "progress_percentage",
            "is_overdue",
            "primary_manager_id",
            "primary_manager_name",
            "current_phase_name",
            "created_by_id",
            "created_at",
            "updated_at",
        ]

    def get_progress_percentage(self, project) -> float:
        return calculate_project_progress(project)

    def get_image_available(self, project) -> bool:
        return bool(project.image)

    def get_is_overdue(self, project) -> bool:
        from django.utils import timezone

        return bool(
            project.expected_completion_date < timezone.localdate()
            and project.status
            not in {Project.Status.COMPLETED, Project.Status.OPERATIONAL}
        )

    def get_primary_manager_id(self, project) -> str | None:
        return next(
            (
                assignment.user_id
                for assignment in project.assignments.all()
                if assignment.role_type == ProjectAssignment.RoleType.PRIMARY_MANAGER
                and assignment.is_active
            ),
            None,
        )

    def get_primary_manager_name(self, project) -> str | None:
        return next(
            (
                assignment.user.full_name
                for assignment in project.assignments.all()
                if assignment.role_type == ProjectAssignment.RoleType.PRIMARY_MANAGER
                and assignment.is_active
            ),
            None,
        )

    def get_current_phase_name(self, project) -> str | None:
        phases = sorted(project.phases.all(), key=lambda phase: phase.sequence_number)
        current = next(
            (phase for phase in phases if phase.status == ProjectPhase.Status.IN_PROGRESS),
            None,
        ) or next(
            (phase for phase in phases if phase.status == ProjectPhase.Status.NOT_STARTED),
            None,
        )
        return current.name if current else None


class ProjectWriteSerializer(serializers.ModelSerializer):
    primary_manager_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(
            status=User.STATUS_ACTIVE,
            role__name=Role.CONSTRUCTION_MANAGER,
        ),
        required=False,
        write_only=True,
    )
    facility = serializers.PrimaryKeyRelatedField(
        queryset=Facility.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Project
        fields = [
            "name",
            "facility",
            "facility_type",
            "description",
            "location",
            "latitude",
            "longitude",
            "image",
            "start_date",
            "expected_completion_date",
            "primary_manager_id",
        ]

    def validate(self, attrs):
        if self.instance and "facility" in attrs:
            incoming_id = getattr(attrs["facility"], "pk", None)
            if incoming_id != self.instance.facility_id:
                raise serializers.ValidationError(
                    {"facility": "A project's facility cannot be changed by update."}
                )
        return attrs

    @staticmethod
    def _set_primary_manager(project, manager, actor):
        assignments = list(
            ProjectAssignment.all_objects.select_for_update().filter(
                project=project,
                role_type=ProjectAssignment.RoleType.PRIMARY_MANAGER,
            )
        )
        selected = next(
            (assignment for assignment in assignments if assignment.user_id == manager.pk),
            None,
        )
        for assignment in assignments:
            if assignment.is_active and assignment.pk != getattr(selected, "pk", None):
                assignment.soft_delete()

        if selected:
            if not selected.is_active:
                selected.is_active = True
                try:
                    selected.full_clean()
                except DjangoValidationError as exc:
                    _raise_drf_validation(exc)
                selected.save(update_fields=["is_active", "updated_at"])
            return selected

        assignment = ProjectAssignment(
            project=project,
            user=manager,
            role_type=ProjectAssignment.RoleType.PRIMARY_MANAGER,
            created_by=actor,
        )
        try:
            assignment.full_clean()
        except DjangoValidationError as exc:
            _raise_drf_validation(exc)
        assignment.save()
        return assignment

    @transaction.atomic
    def create(self, validated_data):
        manager = validated_data.pop("primary_manager_id", None)
        project = Project(
            **validated_data,
            created_by=self.context["request"].user,
        )
        try:
            project.full_clean()
        except DjangoValidationError as exc:
            _raise_drf_validation(exc)
        project.save()
        if manager is not None:
            self._set_primary_manager(
                project,
                manager,
                self.context["request"].user,
            )
        return project

    @transaction.atomic
    def update(self, instance, validated_data):
        manager = validated_data.pop("primary_manager_id", None)
        instance = Project.objects.select_for_update().get(pk=instance.pk)
        for field_name, value in validated_data.items():
            setattr(instance, field_name, value)
        try:
            instance.full_clean()
        except DjangoValidationError as exc:
            _raise_drf_validation(exc)
        instance.save()
        if manager is not None:
            self._set_primary_manager(
                instance,
                manager,
                self.context["request"].user,
            )
        return instance


class ProjectAssignmentSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(
            status=User.STATUS_ACTIVE,
            role__name=Role.CONSTRUCTION_MANAGER,
        )
    )
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    created_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ProjectAssignment
        fields = [
            "id",
            "user",
            "user_name",
            "user_email",
            "role_type",
            "created_by_id",
            "created_at",
            "is_active",
        ]
        read_only_fields = ["id", "created_by_id", "created_at", "is_active"]


class CompleteProjectSerializer(serializers.Serializer):
    actual_completion_date = serializers.DateField()


class FacilityConversionSerializer(serializers.ModelSerializer):
    created_from_project_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Facility
        fields = [
            "id",
            "created_from_project_id",
            "name",
            "type",
            "location",
            "status",
            "created_at",
        ]
