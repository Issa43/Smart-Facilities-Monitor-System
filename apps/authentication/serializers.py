from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from apps.notifications.services import setting_enabled
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User


class SFLMSTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Login serializer (email + password -> access + refresh tokens).

    - Uses `email` as the login field (User.USERNAME_FIELD).
    - Rejects suspended/inactive accounts explicitly with a clear message
      instead of the generic "no active account" DRF SimpleJWT default.
    - Embeds role/full_name claims in the access token so the frontend can
      render role-based UI without an extra `/me` round-trip on load.
    """

    username_field = User.USERNAME_FIELD

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["full_name"] = user.full_name
        token["role"] = user.role.name if user.role_id else None
        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        if self.user.status != User.STATUS_ACTIVE:
            raise serializers.ValidationError(
                "This account is not active. Contact your Super Admin."
            )

        data["user"] = {
            "id": str(self.user.id),
            "full_name": self.user.full_name,
            "email": self.user.email,
            "role": self.user.role.name if self.user.role_id else None,
        }
        return data


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def save(self, **kwargs):
        try:
            token = RefreshToken(self.validated_data["refresh"])
            token.blacklist()
        except Exception as exc:  # noqa: BLE001 - surfaced as a validation error below
            raise serializers.ValidationError({"refresh": "Invalid or already-used refresh token."}) from exc


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )
        try:
            user_id = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=user_id, status=User.STATUS_ACTIVE)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist) as exc:
            raise serializers.ValidationError(
                {"token": "This password reset link is invalid or expired."}
            ) from exc
        if setting_enabled("security.passwordPolicy"):
            try:
                validate_password(attrs["new_password"], user=user)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(
                    {"new_password": exc.messages}
                ) from exc
        attrs["user"] = user
        return attrs
