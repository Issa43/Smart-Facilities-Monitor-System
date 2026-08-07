from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import LogoutSerializer, SFLMSTokenObtainPairSerializer


class LoginView(TokenObtainPairView):
    """POST /api/auth/login/  ->  { access, refresh, user: {...} }"""

    permission_classes = [AllowAny]
    serializer_class = SFLMSTokenObtainPairSerializer


class RefreshView(TokenRefreshView):
    """POST /api/auth/refresh/  ->  { access, refresh (rotated) }"""

    permission_classes = [AllowAny]


class LogoutView(APIView):
    """POST /api/auth/logout/  { refresh } -> blacklists the refresh token."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Logged out successfully."}, status=status.HTTP_205_RESET_CONTENT)
