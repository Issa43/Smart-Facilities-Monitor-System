"""Bounded, fail-closed HTTPS JSON client for approved hazard providers.

Uses only the standard library (no new dependency). Every failure is raised
as a sanitized ``ProviderError`` whose message is a short code; request URLs,
headers, and response bodies are never included in exceptions or logs.
"""

import json
import socket
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .base import MalformedProviderPayload, ProviderRateLimited, ProviderUnavailable


USER_AGENT = "SFLMS-SafetyAlerts/1.0"
READ_CHUNK_BYTES = 64 * 1024
MAX_RETRY_AFTER_SECONDS = 3600


def _host_allowed(url, allowed_hosts):
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return bool(
        parts.scheme == "https"
        and not parts.username
        and not parts.password
        and parts.port in (None, 443)
        and (parts.hostname or "").lower() in allowed_hosts
    )


class _AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects only to https URLs on the same allowlisted hosts."""

    max_redirections = 3

    def __init__(self, allowed_hosts):
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _host_allowed(newurl, self.allowed_hosts):
            raise ProviderUnavailable("redirect_rejected", retryable=False)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(request, *, timeout, allowed_hosts):
    opener = urllib.request.build_opener(_AllowlistRedirectHandler(allowed_hosts))
    return opener.open(request, timeout=timeout)


def _retry_after_seconds(headers):
    raw = (headers or {}).get("Retry-After", "") if headers is not None else ""
    try:
        seconds = int(str(raw).strip())
    except (TypeError, ValueError):
        seconds = 0
    return max(0, min(seconds, MAX_RETRY_AFTER_SECONDS))


def _now():
    return time.monotonic()


def _read_bounded(response, *, max_bytes, deadline):
    chunks = []
    total = 0
    while True:
        if _now() > deadline:
            raise ProviderUnavailable("timeout")
        chunk = response.read(READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise MalformedProviderPayload("payload_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_json(url, *, allowed_hosts, timeout_seconds, max_bytes):
    """GET an approved provider URL and return decoded JSON.

    Raises ProviderUnavailable (network, timeout, HTTP status, disallowed
    endpoint), ProviderRateLimited (HTTP 429), or MalformedProviderPayload
    (wrong content type, oversized, or undecodable body).
    """

    body = fetch_body(
        url,
        allowed_hosts=allowed_hosts,
        timeout_seconds=timeout_seconds,
        max_bytes=max_bytes,
        accept="application/json, application/geo+json",
        content_type_token="json",
    )
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise MalformedProviderPayload("invalid_json") from None


def fetch_body(
    url,
    *,
    allowed_hosts,
    timeout_seconds,
    max_bytes,
    accept,
    content_type_token,
):
    """GET an approved provider URL and return the raw bounded body.

    Shared by every provider transport so the host allowlist, https-only rule,
    redirect policy, timeout and byte cap are enforced in exactly one place.
    """

    allowed_hosts = {host.lower() for host in allowed_hosts}
    if not _host_allowed(url, allowed_hosts):
        # Fail closed before any network activity.
        raise ProviderUnavailable("endpoint_not_allowed", retryable=False)

    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Accept": accept, "User-Agent": USER_AGENT},
    )
    deadline = _now() + timeout_seconds
    try:
        with _open(request, timeout=timeout_seconds, allowed_hosts=allowed_hosts) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise ProviderUnavailable(f"http_{status}", retryable=500 <= status < 600)
            final_url = response.geturl() if hasattr(response, "geturl") else url
            if not _host_allowed(final_url, allowed_hosts):
                raise ProviderUnavailable("redirect_rejected", retryable=False)
            content_type = (response.headers.get("Content-Type") or "").lower()
            if content_type and content_type_token not in content_type:
                raise MalformedProviderPayload("unexpected_content_type")
            body = _read_bounded(response, max_bytes=max_bytes, deadline=deadline)
    except (ProviderUnavailable, ProviderRateLimited, MalformedProviderPayload):
        raise
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise ProviderRateLimited(_retry_after_seconds(exc.headers)) from None
        raise ProviderUnavailable(f"http_{exc.code}", retryable=500 <= exc.code < 600) from None
    except (socket.timeout, TimeoutError):
        raise ProviderUnavailable("timeout") from None
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        code = "timeout" if isinstance(reason, (socket.timeout, TimeoutError)) else "network_error"
        raise ProviderUnavailable(code) from None
    except (ConnectionError, OSError):
        raise ProviderUnavailable("network_error") from None

    return body
