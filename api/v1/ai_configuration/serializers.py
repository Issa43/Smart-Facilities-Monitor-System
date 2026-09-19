from rest_framework import serializers

from apps.security.models import (
    AuthorizedVehicle,
    Camera,
    CameraAIModel,
    CameraROI,
    RestrictedZoneSchedule,
    VirtualLine,
)


class StrictModelSerializer(serializers.ModelSerializer):
    def to_internal_value(self, data):
        if not hasattr(data, "keys"):
            raise serializers.ValidationError("Expected an object payload.")
        unknown = sorted(set(data.keys()) - set(self.fields))
        if unknown:
            raise serializers.ValidationError(
                {field: "This field is not allowed." for field in unknown}
            )
        return super().to_internal_value(data)


class CameraROIReadSerializer(serializers.ModelSerializer):
    camera_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = CameraROI
        fields = [
            "id",
            "camera_id",
            "identifier",
            "name",
            "polygon",
            "is_active",
            "created_at",
            "updated_at",
        ]


class CameraROICreateSerializer(StrictModelSerializer):
    camera = serializers.PrimaryKeyRelatedField(queryset=Camera.objects.all())

    class Meta:
        model = CameraROI
        fields = ["camera", "identifier", "name", "polygon"]


class CameraROIUpdateSerializer(StrictModelSerializer):
    class Meta:
        model = CameraROI
        fields = ["name", "polygon"]
        extra_kwargs = {
            "name": {"required": False},
            "polygon": {"required": False},
        }


class RestrictedScheduleReadSerializer(serializers.ModelSerializer):
    roi_id = serializers.UUIDField(read_only=True)
    camera_id = serializers.UUIDField(source="roi.camera_id", read_only=True)
    crosses_midnight = serializers.BooleanField(read_only=True)

    class Meta:
        model = RestrictedZoneSchedule
        fields = [
            "id",
            "roi_id",
            "camera_id",
            "always_restricted",
            "from_time",
            "to_time",
            "days_of_week",
            "timezone_name",
            "crosses_midnight",
            "is_active",
            "created_at",
            "updated_at",
        ]


class RestrictedScheduleCreateSerializer(StrictModelSerializer):
    roi = serializers.PrimaryKeyRelatedField(queryset=CameraROI.objects.all())

    class Meta:
        model = RestrictedZoneSchedule
        fields = [
            "roi",
            "always_restricted",
            "from_time",
            "to_time",
            "days_of_week",
            "timezone_name",
        ]


class RestrictedScheduleUpdateSerializer(StrictModelSerializer):
    class Meta:
        model = RestrictedZoneSchedule
        fields = [
            "always_restricted",
            "from_time",
            "to_time",
            "days_of_week",
            "timezone_name",
        ]
        extra_kwargs = {
            "always_restricted": {"required": False},
            "from_time": {"required": False},
            "to_time": {"required": False},
            "days_of_week": {"required": False},
            "timezone_name": {"required": False},
        }


class VirtualLineReadSerializer(serializers.ModelSerializer):
    camera_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = VirtualLine
        fields = [
            "id",
            "camera_id",
            "line_start",
            "line_end",
            "is_active",
            "created_at",
            "updated_at",
        ]


class VirtualLineCreateSerializer(StrictModelSerializer):
    camera = serializers.PrimaryKeyRelatedField(queryset=Camera.objects.all())

    class Meta:
        model = VirtualLine
        fields = ["camera", "line_start", "line_end"]


class VirtualLineUpdateSerializer(StrictModelSerializer):
    class Meta:
        model = VirtualLine
        fields = ["line_start", "line_end"]
        extra_kwargs = {
            "line_start": {"required": False},
            "line_end": {"required": False},
        }


class AuthorizedVehicleReadSerializer(serializers.ModelSerializer):
    currently_authorized = serializers.BooleanField(
        source="is_currently_authorized", read_only=True
    )

    class Meta:
        model = AuthorizedVehicle
        fields = [
            "id",
            "plate_number",
            "responsible_name",
            "expires_on",
            "currently_authorized",
            "is_active",
            "created_at",
            "updated_at",
        ]


class MachineAuthorizedVehicleSerializer(serializers.ModelSerializer):
    authorized = serializers.BooleanField(source="is_currently_authorized", read_only=True)

    class Meta:
        model = AuthorizedVehicle
        fields = ["id", "plate_number", "expires_on", "authorized", "updated_at"]


class AuthorizedVehicleWriteSerializer(StrictModelSerializer):
    class Meta:
        model = AuthorizedVehicle
        fields = ["plate_number", "responsible_name", "expires_on"]


class CameraAIModelReadSerializer(serializers.ModelSerializer):
    camera_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = CameraAIModel
        fields = ["id", "camera_id", "model_identifier", "is_active", "updated_at"]


class CameraAIModelInputSerializer(serializers.Serializer):
    model_identifier = serializers.ChoiceField(
        choices=CameraAIModel.ModelIdentifier.choices
    )
