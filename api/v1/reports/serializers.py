from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.reverse import reverse

from apps.reports.models import Report, ReportTemplate
from apps.reports.services import validate_template_configuration

from .permissions import report_modules_for_user


def raise_drf_validation(error):
    details = getattr(error, "message_dict", None) or {
        "non_field_errors": error.messages
    }
    raise serializers.ValidationError(details) from error


class StrictInputSerializer(serializers.Serializer):
    """Reject fields outside the explicit API contract."""

    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unknown = set(data.keys()) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {field: "This field is not accepted." for field in sorted(unknown)}
                )
        return super().to_internal_value(data)


class ReportTemplateReadSerializer(serializers.ModelSerializer):
    created_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ReportTemplate
        fields = [
            "id",
            "name",
            "module",
            "format",
            "configuration",
            "created_by_id",
            "created_at",
            "updated_at",
        ]


class ReportTemplateCreateSerializer(StrictInputSerializer):
    name = serializers.CharField(max_length=255, trim_whitespace=True)
    module = serializers.ChoiceField(choices=ReportTemplate.Module.choices)
    format = serializers.ChoiceField(choices=ReportTemplate.Format.choices)
    configuration = serializers.JSONField()

    def validate_configuration(self, value):
        try:
            return validate_template_configuration(value)
        except DjangoValidationError as exc:
            raise_drf_validation(exc)


class ReportTemplateUpdateSerializer(StrictInputSerializer):
    name = serializers.CharField(
        max_length=255,
        trim_whitespace=True,
        required=False,
    )
    configuration = serializers.JSONField(required=False)

    def validate_configuration(self, value):
        try:
            return validate_template_configuration(value)
        except DjangoValidationError as exc:
            raise_drf_validation(exc)


class ReportRequestCreateSerializer(StrictInputSerializer):
    type = serializers.CharField(max_length=100, trim_whitespace=True)
    module = serializers.ChoiceField(choices=Report.Module.choices)
    format = serializers.ChoiceField(choices=Report.Format.choices)
    parameters = serializers.JSONField(default=dict)
    template = serializers.PrimaryKeyRelatedField(
        queryset=ReportTemplate.objects.none(),
        required=False,
        allow_null=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request:
            self.fields["template"].queryset = ReportTemplate.objects.filter(
                module__in=report_modules_for_user(request.user)
            )

    def validate_parameters(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Report parameters must be an object.")
        if any(str(key).startswith("_") for key in value):
            raise serializers.ValidationError(
                "Parameter names beginning with '_' are reserved by the report service."
            )
        return value

    def validate(self, attrs):
        template = attrs.get("template")
        if template and (
            template.module != attrs["module"] or template.format != attrs["format"]
        ):
            raise serializers.ValidationError(
                {"template": "Template module and format must match the report."}
            )
        return attrs


class ReportRequestReadSerializer(serializers.ModelSerializer):
    created_by_id = serializers.UUIDField(read_only=True)
    parameters = serializers.SerializerMethodField()
    failure_details = serializers.SerializerMethodField()
    download_available = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            "id",
            "type",
            "module",
            "parameters",
            "format",
            "status",
            "failure_details",
            "download_available",
            "download_url",
            "created_by_id",
            "created_at",
            "updated_at",
        ]

    def get_parameters(self, report) -> dict:
        return {
            key: value
            for key, value in report.parameters.items()
            if not str(key).startswith("_")
        }

    def get_failure_details(self, report) -> str | None:
        if report.status != Report.Status.FAILED:
            return None
        return report.parameters.get("_generation_error")

    def get_download_available(self, report) -> bool:
        return bool(report.status == Report.Status.COMPLETED and report.file_path)

    def get_download_url(self, report) -> str | None:
        if not self.get_download_available(report):
            return None
        return reverse(
            "api_v1:report-request-download",
            kwargs={"pk": report.pk},
            request=self.context.get("request"),
        )
