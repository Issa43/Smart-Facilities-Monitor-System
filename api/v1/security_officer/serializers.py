from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework.reverse import reverse

from apps.attachments.models import Attachment
from apps.facilities.models import Facility
from apps.security.models import Camera, Incident, IncidentAction, IncidentNote, SafetyDocument, SecurityAlert
from apps.users.models import User

from .permissions import facilities_for_security_user


def _raise_drf_validation(error):
    details = getattr(error, "message_dict", None) or {
        "non_field_errors": error.messages
    }
    raise serializers.ValidationError(details) from error


class SecurityAlertReadSerializer(serializers.ModelSerializer):
    facility_id = serializers.UUIDField(read_only=True)
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    reviewed_by_id = serializers.UUIDField(read_only=True)
    created_by_id = serializers.UUIDField(read_only=True)
    snapshot_available = serializers.SerializerMethodField()
    snapshot_download_url = serializers.SerializerMethodField()
    camera_event_id = serializers.SerializerMethodField()
    event_type = serializers.SerializerMethodField()
    camera_id = serializers.SerializerMethodField()
    camera_code = serializers.SerializerMethodField()
    roi_id = serializers.SerializerMethodField()
    roi_identifier = serializers.SerializerMethodField()

    class Meta:
        model = SecurityAlert
        fields = [
            "id",
            "facility_id",
            "facility_name",
            "alert_type",
            "location",
            "severity_level",
            "source",
            "confidence_score",
            "camera_event_id",
            "event_type",
            "camera_id",
            "camera_code",
            "roi_id",
            "roi_identifier",
            "snapshot_available",
            "snapshot_download_url",
            "status",
            "is_false_positive",
            "reviewed_by_id",
            "review_notes",
            "created_by_id",
            "created_at",
            "updated_at",
        ]

    def get_snapshot_available(self, alert) -> bool:
        if alert.snapshot_image:
            return True
        try:
            return bool(alert.camera_event.snapshot_path)
        except ObjectDoesNotExist:
            return False

    def get_snapshot_download_url(self, alert) -> str | None:
        if not self.get_snapshot_available(alert):
            return None
        return reverse(
            "api_v1:security-alert-snapshot",
            kwargs={"pk": alert.pk},
            request=self.context.get("request"),
        )

    @staticmethod
    def _event(alert):
        try:
            return alert.camera_event
        except ObjectDoesNotExist:
            return None

    @extend_schema_field(OpenApiTypes.UUID)
    def get_camera_event_id(self, alert):
        event = self._event(alert)
        return event.pk if event else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_event_type(self, alert):
        event = self._event(alert)
        return event.event_type if event else None

    @extend_schema_field(OpenApiTypes.UUID)
    def get_camera_id(self, alert):
        event = self._event(alert)
        return event.camera_id if event else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_camera_code(self, alert):
        event = self._event(alert)
        return event.camera.code if event else None

    @extend_schema_field(OpenApiTypes.UUID)
    def get_roi_id(self, alert):
        event = self._event(alert)
        return event.roi_id if event else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_roi_identifier(self, alert):
        event = self._event(alert)
        return event.roi.identifier if event and event.roi_id else None


class AlertReviewInputSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class AlertDismissInputSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)


class AlertConversionInputSerializer(serializers.Serializer):
    incident_type = serializers.CharField(allow_blank=False, trim_whitespace=True)
    description = serializers.CharField(allow_blank=False, trim_whitespace=True)
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(status=User.STATUS_ACTIVE),
        required=False,
        allow_null=True,
    )


@extend_schema_serializer(component_name="SecurityIncidentRead")
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


class ManualIncidentInputSerializer(serializers.Serializer):
    facility = serializers.PrimaryKeyRelatedField(queryset=Facility.objects.none())
    incident_type = serializers.CharField(allow_blank=False, trim_whitespace=True)
    description = serializers.CharField(allow_blank=False, trim_whitespace=True)
    location = serializers.CharField(allow_blank=False, trim_whitespace=True)
    severity_level = serializers.ChoiceField(choices=Incident.Severity.choices)
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(status=User.STATUS_ACTIVE),
        required=False,
        allow_null=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request:
            self.fields["facility"].queryset = facilities_for_security_user(
                request.user
            )


class IncidentInvestigationInputSerializer(serializers.Serializer):
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(status=User.STATUS_ACTIVE),
        required=False,
        allow_null=True,
    )


class IncidentTransferInputSerializer(serializers.Serializer):
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(status=User.STATUS_ACTIVE),
    )


class IncidentCloseInputSerializer(serializers.Serializer):
    final_report = serializers.CharField(allow_blank=False, trim_whitespace=True)


class IncidentActionInputSerializer(serializers.Serializer):
    action_taken = serializers.CharField(allow_blank=False, trim_whitespace=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


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
            "completed_at",
            "completed_by_id",
            "created_by_id",
            "created_at",
        ]


class IncidentActionCompletionSerializer(serializers.Serializer):
    completed = serializers.BooleanField()


class EvidenceUploadSerializer(serializers.Serializer):
    file = serializers.FileField(write_only=True)

    def create(self, validated_data):
        attachment = Attachment(
            entity_type=self.context["entity_type"],
            entity_id=self.context["entity_id"],
            file=validated_data["file"],
            created_by=self.context["request"].user,
        )
        try:
            attachment.save()
        except DjangoValidationError as exc:
            _raise_drf_validation(exc)
        return attachment


class EvidenceReadSerializer(serializers.ModelSerializer):
    created_by_id = serializers.UUIDField(read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = [
            "id",
            "entity_type",
            "entity_id",
            "original_file_name",
            "file_type",
            "mime_type",
            "file_size",
            "created_by_id",
            "created_at",
            "download_url",
        ]

    def get_download_url(self, attachment) -> str:
        return reverse(
            "api_v1:security-evidence-download",
            kwargs={"pk": attachment.pk},
            request=self.context.get("request"),
        )


class IncidentNoteInputSerializer(serializers.Serializer):
    body = serializers.CharField(allow_blank=False, trim_whitespace=True)


class IncidentNoteReadSerializer(serializers.ModelSerializer):
    incident_id = serializers.UUIDField(read_only=True)
    author_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = IncidentNote
        fields = ["id", "incident_id", "body", "author_id", "created_at"]


class SecurityFacilitySerializer(serializers.ModelSerializer):
    created_from_project_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = Facility
        fields = ["id", "created_from_project_id", "name", "type", "location", "operation_start_date", "status", "created_at", "updated_at"]


class CameraSerializer(serializers.ModelSerializer):
    facility_id = serializers.UUIDField(read_only=True)
    stream_available = serializers.SerializerMethodField()

    class Meta:
        model = Camera
        fields = ["id", "facility_id", "code", "name", "zone", "status", "last_seen_at", "stream_available", "created_at", "updated_at"]

    def get_stream_available(self, obj) -> bool:
        return bool(obj.stream_reference and obj.status == Camera.Status.ONLINE)


class SafetyDocumentSerializer(serializers.ModelSerializer):
    facility_id = serializers.UUIDField(read_only=True)
    uploaded_by_id = serializers.UUIDField(source="created_by_id", read_only=True)
    uploaded_at = serializers.DateTimeField(source="created_at", read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = SafetyDocument
        fields = ["id", "facility", "facility_id", "title", "category", "file", "original_file_name", "mime_type", "file_size", "uploaded_by_id", "uploaded_at", "download_url"]
        extra_kwargs = {"facility": {"write_only": True}, "file": {"write_only": True}, "original_file_name": {"read_only": True}, "mime_type": {"read_only": True}, "file_size": {"read_only": True}}

    def get_download_url(self, obj) -> str | None:
        request = self.context.get("request")
        return request.build_absolute_uri(f"/api/v1/security/documents/{obj.pk}/download/") if request else None
