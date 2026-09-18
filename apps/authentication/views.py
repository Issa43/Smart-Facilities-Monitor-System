import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.http import Http404
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
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
    SFLMSTokenRefreshSerializer,
)


logger = logging.getLogger(__name__)


class LoginView(TokenObtainPairView):
    """POST /api/auth/login/  ->  { access, refresh, user: {...} }"""

    permission_classes = [AllowAny]
    serializer_class = SFLMSTokenObtainPairSerializer


class RefreshView(TokenRefreshView):
    """POST /api/auth/refresh/  ->  { access, refresh (rotated) }"""

    permission_classes = [AllowAny]
    serializer_class = SFLMSTokenRefreshSerializer


class LogoutView(GenericAPIView):
    """POST /api/auth/logout/  { refresh } -> blacklists the refresh token."""

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = LogoutSerializer

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Logged out successfully."}, status=status.HTTP_205_RESET_CONTENT)


def build_password_reset_url(user):
    """The frontend reset link for one account.

    Single source of truth for the uid encoding, the token generator and the
    configured frontend URL, so the emailed link and any other caller can never
    drift apart. Generating a link changes nothing: the token is derived from
    the account's current state, not stored.
    """

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return settings.FRONTEND_PASSWORD_RESET_URL.format(uid=uid, token=token)


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
            frontend_url = build_password_reset_url(user)
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
        user.set_password(payload.validated_data["new_password"])
        user.save(update_fields=["password"])
        record_audit(
            actor=user,
            action="authentication.password_reset",
            entity=user,
            after={"method": "email_token"},
        )
        return Response({"detail": "Password updated successfully."})


class DevPasswordResetLinkView(GenericAPIView):
    """Local-development shortcut that returns a reset link directly.

    Nothing is emailed: the link is returned in the response body, so this view
    makes no SMTP connection and works whether or not a local mail sink is
    running. It is **not** a second reset mechanism either: it mints exactly the
    same uid/token pair the email flow uses, through
    :func:`build_password_reset_url`, and the password itself is still changed
    only by the normal confirmation endpoint.

    Production safety: the view refuses to run unless ``settings.DEBUG`` is on,
    answering with the same 404 an unrouted path would give. The check is here
    on the server rather than in the client, and production settings pin
    ``DEBUG = False``. It is also hidden from the published API schema.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = PasswordResetRequestSerializer

    @extend_schema(exclude=True)
    def post(self, request):
        if not settings.DEBUG:
            # Indistinguishable from the route not existing at all.
            raise Http404
        payload = PasswordResetRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        user = User.objects.filter(
            email__iexact=payload.validated_data["email"],
            status=User.STATUS_ACTIVE,
        ).first()
        if user is None:
            # No account fields are echoed back, only that nothing was issued.
            return Response(
                {"detail": "No eligible active account for that email."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"reset_url": build_password_reset_url(user)})
