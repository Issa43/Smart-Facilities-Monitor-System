import itertools
import socket
import urllib.error
import urllib.request
from email.message import Message
from unittest.mock import patch

import pytest

from apps.safety.providers import http
from apps.safety.providers.base import (
    MalformedProviderPayload,
    ProviderRateLimited,
    ProviderUnavailable,
)


ALLOWED = {"earthquake.usgs.gov"}
URL = "https://earthquake.usgs.gov/feed.geojson?secret=do-not-log"


class FakeResponse:
    def __init__(self, body=b'{"type": "FeatureCollection", "features": []}', *, status=200, content_type="application/json", url=URL):
        self._body = body
        self._offset = 0
        self.status = status
        self.headers = {"Content-Type": content_type}
        self._url = url

    def read(self, size):
        chunk = self._body[self._offset:self._offset + size]
        self._offset += size
        return chunk

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fetch(url=URL, **overrides):
    options = {"allowed_hosts": ALLOWED, "timeout_seconds": 5, "max_bytes": 1024 * 1024}
    options.update(overrides)
    return http.fetch_json(url, **options)


def _assert_sanitized(exc):
    text = f"{exc} {exc!r} {exc.args}"
    assert "secret" not in text and "earthquake.usgs.gov" not in text
    assert exc.__suppress_context__ or exc.__cause__ is None


@pytest.mark.parametrize(
    "url",
    [
        "http://earthquake.usgs.gov/feed.geojson",
        "https://evil.example/feed.geojson",
        "https://user:pw@earthquake.usgs.gov/feed.geojson",
        "https://earthquake.usgs.gov:8443/feed.geojson",
        "file:///etc/passwd",
        "not a url",
    ],
)
def test_disallowed_endpoints_fail_closed_before_any_network_call(url):
    with patch.object(http, "_open") as opener:
        with pytest.raises(ProviderUnavailable) as caught:
            fetch(url=url)
    opener.assert_not_called()
    assert caught.value.code == "endpoint_not_allowed" and caught.value.retryable is False


def test_successful_json_response_is_decoded_with_explicit_timeout():
    with patch.object(http, "_open", return_value=FakeResponse()) as opener:
        assert fetch() == {"type": "FeatureCollection", "features": []}
    request = opener.call_args.args[0]
    assert opener.call_args.kwargs["timeout"] == 5
    assert request.get_method() == "GET"
    assert request.get_header("User-agent") == http.USER_AGENT
    assert request.get_header("Authorization") is None


@pytest.mark.parametrize(
    "response,code",
    [
        (FakeResponse(b"x" * 2048), "payload_too_large"),
        (FakeResponse(b"{not json"), "invalid_json"),
        (FakeResponse(b"\xff\xfe"), "invalid_json"),
        (FakeResponse(b"<html>error</html>", content_type="text/html"), "unexpected_content_type"),
    ],
)
def test_bad_bodies_are_rejected_as_malformed(response, code):
    with patch.object(http, "_open", return_value=response):
        with pytest.raises(MalformedProviderPayload) as caught:
            fetch(max_bytes=1024)
    assert caught.value.code == code


def _http_error(code, headers=None):
    message = Message()
    for key, value in (headers or {}).items():
        message[key] = value
    return urllib.error.HTTPError(URL, code, "error", message, None)


@pytest.mark.parametrize("status,retryable", [(500, True), (503, True), (404, False), (403, False)])
def test_http_failures_are_sanitized(status, retryable):
    with patch.object(http, "_open", side_effect=_http_error(status)):
        with pytest.raises(ProviderUnavailable) as caught:
            fetch()
    assert caught.value.code == f"http_{status}"
    assert caught.value.retryable is retryable
    _assert_sanitized(caught.value)


def test_non_200_success_status_is_unavailable():
    with patch.object(http, "_open", return_value=FakeResponse(status=204)):
        with pytest.raises(ProviderUnavailable) as caught:
            fetch()
    assert caught.value.code == "http_204" and not caught.value.retryable


@pytest.mark.parametrize("header,expected", [("120", 120), ("999999", 3600), ("soon", 0)])
def test_rate_limit_retry_after_is_bounded(header, expected):
    with patch.object(http, "_open", side_effect=_http_error(429, {"Retry-After": header})):
        with pytest.raises(ProviderRateLimited) as caught:
            fetch()
    assert caught.value.retry_after_seconds == expected
    _assert_sanitized(caught.value)


@pytest.mark.parametrize(
    "error,code",
    [
        (socket.timeout("timed out"), "timeout"),
        (TimeoutError(), "timeout"),
        (urllib.error.URLError(socket.timeout("timed out")), "timeout"),
        (urllib.error.URLError(f"resolution failed for {URL}"), "network_error"),
        (ConnectionResetError(f"reset {URL}"), "network_error"),
    ],
)
def test_network_failures_and_timeouts_are_retryable_and_sanitized(error, code):
    with patch.object(http, "_open", side_effect=error):
        with pytest.raises(ProviderUnavailable) as caught:
            fetch()
    assert caught.value.code == code and caught.value.retryable
    _assert_sanitized(caught.value)


def test_slow_body_read_hits_overall_deadline():
    clock = itertools.count(start=0, step=10)
    with patch.object(http, "_open", return_value=FakeResponse(b"x" * (3 * http.READ_CHUNK_BYTES))):
        with patch.object(http, "_now", side_effect=lambda: next(clock)):
            with pytest.raises(ProviderUnavailable) as caught:
                fetch(timeout_seconds=15, max_bytes=10 * http.READ_CHUNK_BYTES)
    assert caught.value.code == "timeout"


def test_redirected_final_url_off_allowlist_is_rejected():
    with patch.object(http, "_open", return_value=FakeResponse(url="https://evil.example/x")):
        with pytest.raises(ProviderUnavailable) as caught:
            fetch()
    assert caught.value.code == "redirect_rejected"


def test_redirect_handler_only_follows_allowlisted_https_hosts():
    handler = http._AllowlistRedirectHandler(ALLOWED)
    request = urllib.request.Request(URL)
    followed = handler.redirect_request(request, None, 302, "Found", {}, "https://earthquake.usgs.gov/other")
    assert followed.full_url == "https://earthquake.usgs.gov/other"
    for target in ("https://evil.example/", "http://earthquake.usgs.gov/other"):
        with pytest.raises(ProviderUnavailable):
            handler.redirect_request(request, None, 302, "Found", {}, target)
