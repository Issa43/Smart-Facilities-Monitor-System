from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Permission, Role, User


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "permission_name"]


class RoleSerializer(serializers.ModelSerializer):
    permissions = PermissionSerializer(many=True, read_only=True)
    name_display = serializers.CharField(source="get_name_display", read_only=True)

    class Meta:
        model = Role
        fields = ["id", "name", "name_display", "description", "created_at", "permissions"]
        read_only_fields = ["id", "created_at"]


class UserSerializer(serializers.ModelSerializer):
    """Read serializer - used for list/retrieve/me."""

    role_name = serializers.CharField(source="role.name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "email",
            "phone",
            "username",
            "role",
            "role_name",
            "profile_image",
            "status",
            "last_login",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "last_login", "created_at", "updated_at"]


class UserCreateSerializer(serializers.ModelSerializer):
    """Write serializer used by Super Admin to create users."""

    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "email",
            "phone",
            "username",
            "role",
            "profile_image",
            "status",
            "password",
            "confirm_password",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("confirm_password"):
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """Partial-update serializer - password changes go through a dedicated flow."""

    class Meta:
        model = User
        fields = ["full_name", "phone", "role", "profile_image", "status"]


class UserSelfUpdateSerializer(serializers.ModelSerializer):
    """Self-service profile fields; access-control fields are intentionally excluded."""

    class Meta:
        model = User
        fields = ["full_name", "phone", "profile_image"]
