import math
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

from apps.safety.models import validate_source_url


class ProviderError(Exception):
    """Base class for sanitized provider failures.

    Messages are short machine codes. They never contain request URLs, query
    strings, headers, or response bodies.
    """

    retryable = False

    def __init__(self, code):
        super().__init__(code)
        self.code = code


class ProviderUnavailable(ProviderError):
    """Network failure, timeout, or unsuccessful HTTP status."""

    def __init__(self, code, *, retryable=True):
        super().__init__(code)
        self.retryable = retryable


class ProviderRateLimited(ProviderError):
    """The provider asked the client to slow down."""

    def __init__(self, retry_after_seconds):
        super().__init__("rate_limited")
        self.retry_after_seconds = retry_after_seconds


class MalformedProviderPayload(ProviderError):
    """The whole response is unusable; nothing from it may be ingested."""


class RejectedProviderRecord(ValueError):
    """One provider record is malformed and is skipped individually."""


@dataclass
class ProviderBatch:
    """Normalized events plus per-record accounting for one provider response."""

    provider: str
    events: list = field(default_factory=list)
    records_received: int = 0
    records_malformed: int = 0
    records_unsupported: int = 0
    records_reconciled: int = 0
    reconciliations: list = field(default_factory=list)
    # GDACS earthquakes skipped because USGS is the configured earthquake source.
    records_deferred_to_usgs: int = 0
    deferred_event_ids: list = field(default_factory=list)


def require_mapping(value, name):
    if not isinstance(value, dict):
        raise RejectedProviderRecord(f"{name}_not_object")
    return value


def finite_decimal(value, name, *, required=False, minimum=None, maximum=None):
    if value is None:
        if required:
            raise RejectedProviderRecord(f"{name}_missing")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise RejectedProviderRecord(f"{name}_not_numeric")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RejectedProviderRecord(f"{name}_not_numeric") from exc
    if not number.is_finite():
        raise RejectedProviderRecord(f"{name}_not_finite")
    if (minimum is not None and number < minimum) or (maximum is not None and number > maximum):
        raise RejectedProviderRecord(f"{name}_out_of_range")
    return number


def epoch_milliseconds(value, name, *, required=True):
    if value is None:
        if required:
            raise RejectedProviderRecord(f"{name}_missing")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise RejectedProviderRecord(f"{name}_invalid")
    try:
        return datetime.fromtimestamp(value / 1000, tz=dt_timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise RejectedProviderRecord(f"{name}_invalid") from exc


def utc_datetime(value, name, *, required=True):
    """Parse an ISO-8601 timestamp; naive values are treated as UTC."""

    if value in (None, ""):
        if required:
            raise RejectedProviderRecord(f"{name}_missing")
        return None
    if not isinstance(value, str) or len(value) > 40:
        raise RejectedProviderRecord(f"{name}_invalid")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise RejectedProviderRecord(f"{name}_invalid") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_timezone.utc)
    return parsed.astimezone(dt_timezone.utc)


def bounded_text(value, limit):
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ""
    return " ".join(str(value).split())[:limit]


def safe_source_url(value, provider):
    """Keep a provider page link only if it passes the Phase 1 allowlist.

    The URL is stored for display only and is never fetched server-side.
    """

    if not isinstance(value, str) or not value or len(value) > 500:
        return ""
    try:
        validate_source_url(value, provider)
    except ValidationError:
        return ""
    return value
