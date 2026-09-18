from django.urls import path

from .views import (
    DevPasswordResetLinkView,
    LoginView,
    LogoutView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RefreshView,
)

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="auth-password-reset"),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
    # Local-development shortcut. The route is always present so its refusal is
    # exercised by the test suite, but the view answers 404 unless DEBUG is on,
    # which production settings never allow.
    path(
        "dev/password-reset-link/",
        DevPasswordResetLinkView.as_view(),
        name="auth-dev-password-reset-link",
    ),
]
