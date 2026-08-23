from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.facilities.models import Facility
from apps.projects.models import Project, ProjectAssignment, ProjectPhase
from apps.projects.services import calculate_project_progress
from apps.users.models import Role, User


def _raise_drf_validation(error):
    details = getattr(error, "message_dict", None) or {
        "non_field_errors": error.messages
    }
    raise serializers.ValidationError(details) from error


class ProjectReadSerializer(serializers.ModelSerializer):
    facility_id = serializers.UUIDField(read_only=True)
    created_by_id = serializers.UUIDField(read_only=True)
    progress_percentage = serializers.SerializerMethodField()
    image_available = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    primary_manager_id = serializers.SerializerMethodField()
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
        ]

    def validate(self, attrs):
        if self.instance and "facility" in attrs:
            incoming_id = getattr(attrs["facility"], "pk", None)
            if incoming_id != self.instance.facility_id:
                raise serializers.ValidationError(
                    {"facility": "A project's facility cannot be changed by update."}
                )
        return attrs

    def create(self, validated_data):
        project = Project(
            **validated_data,
            created_by=self.context["request"].user,
        )
        try:
            project.full_clean()
        except DjangoValidationError as exc:
            _raise_drf_validation(exc)
        project.save()
        return project

    def update(self, instance, validated_data):
        for field_name, value in validated_data.items():
            setattr(instance, field_name, value)
        try:
            instance.full_clean()
        except DjangoValidationError as exc:
            _raise_drf_validation(exc)
        instance.save()
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
