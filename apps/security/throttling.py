from rest_framework.throttling import SimpleRateThrottle

from .models import AIIngestionCredential


class AIIngestionRateThrottle(SimpleRateThrottle):
    """Separate throttle bucket for future machine ingestion endpoints."""

    scope = "ai_ingestion"

    def get_cache_key(self, request, view):
        credential = getattr(request, "auth", None)
        if not isinstance(credential, AIIngestionCredential):
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": str(credential.pk),
        }
