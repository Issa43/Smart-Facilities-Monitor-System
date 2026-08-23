from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.common.models import SystemSetting
from apps.common.permissions import IsSuperAdmin
from apps.notifications.models import Notification, NotificationPreference

from .serializers import AuditLogSerializer, NotificationPreferenceSerializer, NotificationSerializer, SystemSettingSerializer


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer
    filterset_fields = ["category", "read_at"]
    search_fields = ["title", "body"]
    ordering_fields = ["created_at", "read_at"]

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Notification.objects.none()
        return Notification.objects.filter(recipient=self.request.user).select_related("recipient__role")

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = self.get_object()
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at", "updated_at"])
        return Response(self.get_serializer(notification).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        updated = self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now(), updated_at=timezone.now())
        return Response({"updated": updated})

    @action(detail=False, methods=["get", "patch"])
    def preferences(self, request):
        preference, _ = NotificationPreference.objects.get_or_create(user=request.user, defaults={"created_by": request.user})
        if request.method == "PATCH":
            serializer = NotificationPreferenceSerializer(preference, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True); serializer.save()
        return Response(NotificationPreferenceSerializer(preference).data)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsSuperAdmin]
    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.select_related("actor").all()
    filterset_fields = {"actor": ["exact"], "action": ["exact"], "entity_type": ["exact"], "created_at": ["date", "gte", "lte"]}
    search_fields = ["action", "entity_type", "entity_id", "entity_ref"]
    ordering_fields = ["created_at", "action", "entity_type"]

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def mine(self, request):
        queryset = self.filter_queryset(
            AuditLog.objects.filter(actor=request.user).select_related("actor")
        )
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)


class SystemSettingViewSet(viewsets.ModelViewSet):
    permission_classes = [IsSuperAdmin]
    serializer_class = SystemSettingSerializer
    queryset = SystemSetting.objects.all()
    lookup_field = "key"
    lookup_value_regex = "[^/]+"
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    search_fields = ["key", "description"]
    ordering_fields = ["key", "updated_at"]

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def effective(self, request):
        values = dict(
            SystemSetting.objects.filter(
                key__in=["security.sessionTimeout"]
            ).values_list("key", "value")
        )
        return Response(
            {
                "session_timeout_enabled": values.get("security.sessionTimeout", True) is True,
                "session_timeout_minutes": 30,
            }
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
