import logging
import uuid

from django.db import transaction
from apps.notifications.services import setting_enabled

from .models import AuditLog


logger = logging.getLogger(__name__)
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class ApiMutationAuditMiddleware:
    """Persist a tamper-resistant envelope for every successful API mutation."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            request.path.startswith("/api/")
            and request.method in MUTATING_METHODS
            and 200 <= response.status_code < 400
            and getattr(request, "user", None)
            and request.user.is_authenticated
            and setting_enabled("security.auditLog")
        ):
            actor = request.user
            method = request.method
            path = request.path[:255]
            status_code = response.status_code
            forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
            ip_address = (
                forwarded.split(",")[0].strip()
                if forwarded
                else request.META.get("REMOTE_ADDR")
            )
            raw_request_id = request.META.get("HTTP_X_REQUEST_ID")
            try:
                request_id = uuid.UUID(raw_request_id) if raw_request_id else None
            except (TypeError, ValueError):
                request_id = None

            def persist():
                try:
                    AuditLog.objects.create(
                        actor=actor,
                        action=f"api.{method.lower()}",
                        entity_type="api_endpoint",
                        entity_id=path[:100],
                        entity_ref=path,
                        after={"status_code": status_code},
                        ip_address=ip_address or None,
                        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
                        request_id=request_id,
                    )
                except Exception:
                    logger.exception("Unable to persist API mutation audit entry")

            transaction.on_commit(persist)
        return response
