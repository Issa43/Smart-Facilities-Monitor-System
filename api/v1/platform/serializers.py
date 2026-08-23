from rest_framework import serializers

from apps.audit.models import AuditLog
from apps.common.models import SystemSetting
from apps.notifications.models import Notification, NotificationPreference


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
