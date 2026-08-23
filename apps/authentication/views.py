import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.audit.services import record_audit
from apps.users.models import User

from .serializers import (
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SFLMSTokenObtainPairSerializer,
)


logger = logging.getLogger(__name__)


class LoginView(TokenObtainPairView):
    """POST /api/auth/login/  ->  { access, refresh, user: {...} }"""

    permission_classes = [AllowAny]
    serializer_class = SFLMSTokenObtainPairSerializer


class RefreshView(TokenRefreshView):
    """POST /api/auth/refresh/  ->  { access, refresh (rotated) }"""

    permission_classes = [AllowAny]


class LogoutView(GenericAPIView):
    """POST /api/auth/logout/  { refresh } -> blacklists the refresh token."""

    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Logged out successfully."}, status=status.HTTP_205_RESET_CONTENT)


class PasswordResetRequestView(GenericAPIView):
    """Issue an enumeration-safe reset email for an active account."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"
    serializer_class = PasswordResetRequestSerializer

    def post(self, request):
        payload = PasswordResetRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        user = User.objects.filter(
            email__iexact=payload.validated_data["email"],
            status=User.STATUS_ACTIVE,
        ).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            frontend_url = settings.FRONTEND_PASSWORD_RESET_URL.format(
                uid=uid,
                token=token,
            )
            try:
                send_mail(
                    subject="Reset your SFLMS password",
                    message=(
                        "A password reset was requested for your SFLMS account. "
                        f"Use this link to choose a new password: {frontend_url}\n\n"
                        "If you did not request this, you can ignore this email."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
            except Exception:
                # Keep the externally visible response enumeration-safe while
                # surfacing delivery failures to production observability.
                logger.exception("Password reset email delivery failed")
        return Response(
            {
                "detail": (
                    "If an active account exists for that email, a reset link "
                    "has been sent."
                )
            },
            status=status.HTTP_202_ACCEPTED,
        )


class PasswordResetConfirmView(GenericAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request):
        payload = PasswordResetConfirmSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        user = payload.validated_data["user"]
        if not default_token_generator.check_token(
            user,
            payload.validated_data["token"],
        ):
            return Response(
                {"token": ["This password reset link is invalid or expired."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.set_password(payload.validated_data["new_password"])
        user.save(update_fields=["password"])
        record_audit(
            actor=user,
            action="authentication.password_reset",
            entity=user,
            after={"method": "email_token"},
        )
        return Response({"detail": "Password updated successfully."})
