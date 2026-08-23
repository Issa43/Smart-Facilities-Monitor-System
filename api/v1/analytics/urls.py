from django.urls import path

from .views import (
    AdminAnalyticsView,
    ConstructionAnalyticsView,
    OperationsAnalyticsView,
    SecurityAnalyticsView,
)


urlpatterns = [
    path("analytics/admin/", AdminAnalyticsView.as_view(), name="analytics-admin"),
    path(
        "analytics/construction/",
        ConstructionAnalyticsView.as_view(),
        name="analytics-construction",
    ),
    path(
        "analytics/operations/",
        OperationsAnalyticsView.as_view(),
        name="analytics-operations",
    ),
    path(
        "analytics/security/",
        SecurityAnalyticsView.as_view(),
        name="analytics-security",
    ),
]
