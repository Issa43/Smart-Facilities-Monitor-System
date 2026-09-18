from rest_framework import serializers

from apps.audit.models import AuditLog
from apps.common.models import SystemSetting
from apps.notifications.models import DeviceRegistration, Notification, NotificationPreference
from apps.notifications.push import register_device


class NotificationSerializer(serializers.ModelSerializer):
    read = serializers.BooleanField(source="is_read", read_only=True)
    audience = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ["id", "title", "body", "category", "tone", "read", "audience", "href", "created_at"]

    def get_audience(self, obj) -> list[str]:
        return [obj.recipient.role.name] if obj.recipient.role_id else []


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = ["low_stock", "overdue_work_orders", "critical_alerts", "stage_review", "updated_at"]
        read_only_fields = ["updated_at"]


class DeviceRegistrationSerializer(serializers.ModelSerializer):
    token = serializers.CharField(
        write_only=True,
        max_length=4096,
        trim_whitespace=False,
    )

    class Meta:
        model = DeviceRegistration
        fields = [
            "id",
            "token",
            "platform",
            "is_active",
            "last_seen_at",
            "disabled_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "is_active",
            "last_seen_at",
            "disabled_at",
            "created_at",
            "updated_at",
        ]

    def validate_token(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("A device registration token is required.")
        return value

    def create(self, validated_data):
        try:
            return register_device(
                user=self.context["request"].user,
                token=validated_data["token"],
                platform=validated_data["platform"],
            )
        except ValueError as exc:
            raise serializers.ValidationError(
                {"token": "This device registration is not available."}
            ) from exc

    def update(self, instance, validated_data):
        try:
            return register_device(
                user=self.context["request"].user,
                token=validated_data.get("token", instance.token),
                platform=validated_data.get("platform", instance.platform),
                instance=instance,
            )
        except ValueError as exc:
            raise serializers.ValidationError(
                {"token": "This device registration is not available."}
            ) from exc


class AuditLogSerializer(serializers.ModelSerializer):
    actor_id = serializers.UUIDField(read_only=True, allow_null=True)
    actor_name = serializers.CharField(source="actor.full_name", read_only=True, allow_null=True)
    entity = serializers.CharField(source="entity_type", read_only=True)
    ip = serializers.IPAddressField(source="ip_address", read_only=True, allow_null=True)

    class Meta:
        model = AuditLog
        fields = ["id", "actor_id", "actor_name", "action", "entity", "entity_ref", "ip", "before", "after", "created_at"]


class SystemSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSetting
        fields = ["id", "key", "value", "description", "version", "updated_at"]
        read_only_fields = ["id", "version", "updated_at"]

    def validate_value(self, value):
        if self.instance is not None and type(value) is not type(self.instance.value):
            raise serializers.ValidationError("The setting value type cannot be changed.")
        return value

    def validate(self, attrs):
        from django.core.exceptions import ValidationError as DjangoValidationError

        from apps.safety.policy import validate_safety_setting

        key = attrs.get("key") or getattr(self.instance, "key", None)
        if "value" in attrs:
            try:
                validate_safety_setting(key, attrs["value"])
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"value": exc.messages}) from exc
        return attrs

    def update(self, instance, validated_data):
        expected_version = self.context["request"].data.get("version")
        if expected_version is None:
            raise serializers.ValidationError({"version": "The current setting version is required."})
        try:
            expected_version = int(expected_version)
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError({"version": "The setting version must be an integer."}) from exc
        if expected_version != instance.version:
            raise serializers.ValidationError({"version": "The setting was updated by another request."})
        instance.value = validated_data.get("value", instance.value)
        instance.description = validated_data.get("description", instance.description)
        instance.version += 1
        instance.save()
        return instance
