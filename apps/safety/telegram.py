"""Minimal outbound-only Telegram client for safety decision messages.

Scope is deliberately one method: ``sendMessage``. There is no webhook, no
``getUpdates``, no command handling, and no way for Telegram to reach the
platform. Nothing Telegram returns can change a safety alert.

The bot token is a secret. It appears only in the request URL that this module
builds and never in an exception, a log record, a return value, or a database
row: urllib attaches the full URL to ``HTTPError``/``URLError``, so every
failure is re-raised as a sanitized :class:`TelegramError` with ``from None``
and originals are never logged.
"""

import json
import socket
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from django.conf import settings


USER_AGENT = "SFLMS-SafetyAlerts/1.0"
MAX_RESPONSE_BYTES = 64 * 1024
MAX_RETRY_AFTER_SECONDS = 3600
# Telegram wording that identifies a destination we must never retry.
_INVALID_CHAT_MARKERS = (
    "chat not found",
    "chat_id is empty",
    "user is deactivated",
    "bot was blocked",
    "bot can't initiate conversation",
    "group chat was upgraded",
    "peer_id_invalid",
)


class TelegramError(Exception):
    """A sanitized send failure. ``code`` is a short, loggable token."""

    def __init__(self, code, *, retryable=False, retry_after=0):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.retry_after = retry_after


class TelegramNotConfigured(TelegramError):
    def __init__(self, code="telegram_not_configured"):
        super().__init__(code, retryable=False)


def is_configured():
    """True when Telegram is switched on and a bot token is present."""

    return bool(
        getattr(settings, "SAFETY_TELEGRAM_ENABLED", False)
        and (getattr(settings, "SAFETY_TELEGRAM_BOT_TOKEN", "") or "").strip()
    )


def _api_url(method):
    base = (getattr(settings, "SAFETY_TELEGRAM_API_BASE_URL", "") or "").rstrip("/")
    token = (getattr(settings, "SAFETY_TELEGRAM_BOT_TOKEN", "") or "").strip()
    if not token:
        raise TelegramNotConfigured()
    parts = urlsplit(base)
    if (
        parts.scheme != "https"
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
        or not parts.hostname
    ):
        # Fail closed: never send a token to a non-https or credentialed host.
        raise TelegramNotConfigured("telegram_endpoint_invalid")
    return f"{base}/bot{token}/{method}"


def _retry_after_seconds(payload, headers):
    raw = ""
    if isinstance(payload, dict):
        parameters = payload.get("parameters")
        if isinstance(parameters, dict):
            raw = parameters.get("retry_after", "")
    if not raw and headers is not None:
        raw = headers.get("Retry-After", "") or ""
    try:
        seconds = int(str(raw).strip())
    except (TypeError, ValueError):
        seconds = 0
    return max(0, min(seconds, MAX_RETRY_AFTER_SECONDS))


def _decode(body):
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _description(payload):
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("description", "")).lower()


def _classify_status(status, payload, headers):
    """Map an HTTP status onto a stable failure code. Never echoes the body."""

    if status == 429:
        return TelegramError(
            "telegram_rate_limited",
            retryable=True,
            retry_after=_retry_after_seconds(payload, headers),
        )
    if 500 <= status < 600:
        return TelegramError(f"telegram_http_{status}", retryable=True)
    if status in (401, 404):
        return TelegramError("telegram_invalid_token", retryable=False)
    description = _description(payload)
    if status == 403 or any(marker in description for marker in _INVALID_CHAT_MARKERS):
        return TelegramError("telegram_invalid_chat", retryable=False)
    if status == 400:
        return TelegramError("telegram_invalid_request", retryable=False)
    return TelegramError(f"telegram_http_{status}", retryable=False)


def send_message(*, chat_id, text):
    """Send one message and return Telegram's message id as a string.

    Raises :class:`TelegramError` for every failure; the caller decides whether
    ``retryable`` warrants another attempt.
    """

    if not is_configured():
        raise TelegramNotConfigured()
    url = _api_url("sendMessage")
    body = json.dumps(
        {
            "chat_id": str(chat_id),
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    timeout = settings.SAFETY_TELEGRAM_TIMEOUT_SECONDS
    try:
        # No redirect handler: Telegram does not redirect, and following one
        # could leak the bot token in the URL to another host.
        opener = urllib.request.build_opener(_NoRedirect())
        with opener.open(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            payload = _decode(response.read(MAX_RESPONSE_BYTES))
            headers = response.headers
    except urllib.error.HTTPError as exc:
        try:
            payload = _decode(exc.read(MAX_RESPONSE_BYTES))
            headers = exc.headers
        except Exception:
            payload, headers = None, None
        raise _classify_status(exc.code, payload, headers) from None
    except (socket.timeout, TimeoutError):
        raise TelegramError("telegram_timeout", retryable=True) from None
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        code = (
            "telegram_timeout"
            if isinstance(reason, (socket.timeout, TimeoutError))
            else "telegram_network_error"
        )
        raise TelegramError(code, retryable=True) from None
    except (ConnectionError, OSError):
        raise TelegramError("telegram_network_error", retryable=True) from None

    if status != 200:
        raise _classify_status(status, payload, headers)
    if payload is None:
        raise TelegramError("telegram_invalid_response", retryable=False)
    if not payload.get("ok"):
        raise _classify_status(int(payload.get("error_code") or 400), payload, headers)
    result = payload.get("result")
    message_id = result.get("message_id") if isinstance(result, dict) else None
    if message_id is None:
        raise TelegramError("telegram_invalid_response", retryable=False)
    return str(message_id)[:64]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise TelegramError("telegram_redirect_rejected", retryable=False)
