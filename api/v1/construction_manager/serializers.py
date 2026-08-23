from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_serializer

from apps.construction.models import DailyReport, QualityInspection, SitePhoto
from apps.materials.models import Material, MaterialConsumptionRecord, MaterialRequest
from apps.projects.models import PhaseProgressLog, PhaseReviewLog, ProjectDocument, ProjectPhase
from api.v1.super_admin.serializers import ProjectReadSerializer


def _raise_drf_validation(error):
    details = getattr(error, "message_dict", None) or {
        "non_field_errors": error.messages
    }
    raise serializers.ValidationError(details) from error


class ProjectPhaseReadSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(read_only=True)
    approved_by_id = serializers.UUIDField(read_only=True)
    created_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ProjectPhase
        fields = [
            "id",
            "project_id",
            "name",
            "description",
            "sequence_number",
            "start_date",
            "expected_completion_date",
            "actual_start_date",
            "actual_completion_date",
            "initial_progress",
            "current_progress",
            "priority",
            "status",
            "approved_by_id",
            "approved_at",
            "created_by_id",
            "created_at",
            "updated_at",
        ]


class ProjectPhaseWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectPhase
        fields = [
            "name",
            "description",
            "sequence_number",
            "start_date",
            "expected_completion_date",
            "priority",
        ]

    def create(self, validated_data):
        phase = ProjectPhase(
            project=self.context["project"],
            created_by=self.context["request"].user,
            **validated_data,
        )
        try:
            phase.full_clean()
        except DjangoValidationError as exc:
            _raise_drf_validation(exc)
        phase.save()
        return phase

    def update(self, instance, validated_data):
        for field_name, value in validated_data.items():
            setattr(instance, field_name, value)
        try:
            instance.full_clean()
        except DjangoValidationError as exc:
            _raise_drf_validation(exc)
        instance.save()
        return instance


class PhaseProgressInputSerializer(serializers.Serializer):
    progress_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    work_completed = serializers.CharField(allow_blank=False, trim_whitespace=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class PhaseProgressLogSerializer(serializers.ModelSerializer):
    phase_id = serializers.UUIDField(read_only=True)
    created_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = PhaseProgressLog
        fields = [
            "id",
            "phase_id",
            "progress_percentage",
            "work_completed",
            "notes",
            "created_by_id",
            "created_at",
        ]


class PhaseReviewInputSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)


class PhaseReviewLogSerializer(serializers.ModelSerializer):
    phase_id = serializers.UUIDField(read_only=True)
    created_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = PhaseReviewLog
        fields = [
            "id",
            "phase_id",
            "decision",
            "disposition",
            "reason",
            "created_by_id",
            "created_at",
        ]


@extend_schema_serializer(component_name="ConstructionMaterial")
class MaterialSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(read_only=True)
    created_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Material
        fields = ["id", "project_id", "name", "unit", "quantity_required", "quantity_used", "quantity_remaining", "min_stock_threshold", "created_by_id", "created_at", "updated_at"]
        read_only_fields = ["quantity_remaining"]

    def validate(self, attrs):
        required = attrs.get("quantity_required", getattr(self.instance, "quantity_required", 0))
        used = attrs.get("quantity_used", getattr(self.instance, "quantity_used", 0))
        attrs["quantity_remaining"] = required - used
        return attrs


class MaterialRequestSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(read_only=True)
    material_name = serializers.CharField(source="material.name", read_only=True)
    unit = serializers.CharField(source="material.unit", read_only=True)
    requested_by_id = serializers.UUIDField(source="created_by_id", read_only=True)

    class Meta:
        model = MaterialRequest
        fields = ["id", "project_id", "material", "material_name", "unit", "quantity_requested", "reason", "priority", "status", "requested_by_id", "created_at", "updated_at"]
        read_only_fields = ["status"]


class MaterialConsumptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaterialConsumptionRecord
        fields = ["id", "material", "quantity_used", "usage_date", "phase", "created_by", "created_at"]
        read_only_fields = ["id", "created_by", "created_at"]


class MaterialConsumptionInputSerializer(serializers.Serializer):
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"))
    usage_date = serializers.DateField(required=False)
    phase = serializers.PrimaryKeyRelatedField(
        queryset=ProjectPhase.objects.all(),
        required=False,
        allow_null=True,
    )


class DailyReportSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(read_only=True)
    phase_id = serializers.UUIDField(read_only=True, allow_null=True)
    author_id = serializers.UUIDField(source="created_by_id", read_only=True)
    summary = serializers.CharField(source="report_content")
    workforce_count = serializers.IntegerField(source="workers_count")
    photo_count = serializers.SerializerMethodField()

    class Meta:
        model = DailyReport
        fields = ["id", "project_id", "phase", "phase_id", "title", "summary", "progress_percentage", "workforce_count", "photo_count", "report_date", "weather_condition", "equipment_used", "issues", "author_id", "created_at", "updated_at"]
        extra_kwargs = {
            "phase": {"required": False, "allow_null": True, "write_only": True},
            "weather_condition": {"required": False, "allow_blank": True, "default": ""},
            "equipment_used": {"required": False, "default": list},
            "issues": {"required": False, "allow_blank": True, "default": ""},
            "report_date": {"required": False},
        }

    def get_photo_count(self, obj) -> int:
        return SitePhoto.objects.filter(project=obj.project, captured_at__date=obj.report_date).count()


class QualityInspectionSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(read_only=True)
    phase_id = serializers.UUIDField(read_only=True)
    inspector_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = QualityInspection
        fields = ["id", "project_id", "phase", "phase_id", "title", "inspector_id", "score", "result", "notes", "inspected_at", "created_at", "updated_at"]
        extra_kwargs = {"phase": {"write_only": True}}


class ProjectDocumentSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(read_only=True)
    uploaded_by_id = serializers.UUIDField(source="created_by_id", read_only=True)
    uploaded_at = serializers.DateTimeField(source="created_at", read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ProjectDocument
        fields = ["id", "project_id", "title", "document_type", "file", "original_file_name", "mime_type", "file_size", "uploaded_by_id", "uploaded_at", "download_url"]
        extra_kwargs = {"file": {"write_only": True}, "original_file_name": {"read_only": True}, "mime_type": {"read_only": True}, "file_size": {"read_only": True}}

    def get_download_url(self, obj) -> str | None:
        request = self.context.get("request")
        return request.build_absolute_uri(f"/api/v1/construction/documents/{obj.pk}/download/") if request else None


class SitePhotoSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(read_only=True)
    phase_id = serializers.UUIDField(read_only=True, allow_null=True)
    download_url = serializers.SerializerMethodField()
    created_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = SitePhoto
        fields = ["id", "project_id", "phase", "phase_id", "image", "caption", "captured_at", "original_file_name", "mime_type", "file_size", "created_by_id", "created_at", "download_url"]
        extra_kwargs = {
            "phase": {"required": False, "allow_null": True, "write_only": True},
            "image": {"write_only": True},
            "captured_at": {"required": False},
            "original_file_name": {"read_only": True},
            "mime_type": {"read_only": True},
            "file_size": {"read_only": True},
        }

    def get_download_url(self, obj) -> str | None:
        request = self.context.get("request")
        return request.build_absolute_uri(f"/api/v1/construction/site-photos/{obj.pk}/download/") if request else None
