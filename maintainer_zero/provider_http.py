"""Explicit, bounded stdlib HTTP transports for non-GitHub providers.

This module intentionally mirrors the injected transport boundary used by
``ReadOnlyProviderClient``.  It is an opt-in GET-only adapter: constructing a
transport performs no I/O, and callers must explicitly invoke it with a
provider-specific allowlisted path.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .github_client import TransportResponse
from .github_metadata import MAX_METADATA_BYTES
from .metadata_provider import SUPPORTED_ADAPTER_PROVIDERS

DEFAULT_MAX_RESPONSE_BYTES = 1_000_000
DEFAULT_MAX_TIMEOUT_SECONDS = 60.0
DEFAULT_USER_AGENT = "maintainer-zero-provider-read-only/0.2.0"
_CONTROL_CHARS = frozenset(chr(code) for code in range(32)) | {chr(127)}
_RESPONSE_HEADERS = frozenset(("link", "retry-after", "x-ratelimit-reset", "x-next-page"))
_MAX_RESPONSE_HEADER_VALUE = 4096
_MAX_PROVIDER_PATH_LENGTH = 256
_SEGMENT = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}"
_GITLAB_PATH = re.compile(
    rf"/api/v4/projects/[1-9][0-9]{{0,9}}(?:/(?:issues|merge_requests|releases))?"
)
_FORGEJO_PATH = re.compile(
    rf"/api/v1/repos/{_SEGMENT}/{_SEGMENT}(?:/(?:issues|pulls|releases)|/pulls/[1-9][0-9]{{0,9}}/reviews)?"
)


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, *args, **kwargs):
        return None


_NO_REDIRECT_OPENER = build_opener(_RejectRedirect)


class ProviderHTTPError(ValueError):
    """Raised when an explicit provider HTTP transport is unsafe."""


@dataclass(frozen=True)
class ProviderHTTPTransportConfig:
    """Boundaries for :class:`ProviderHTTPTransport`."""

    api_base: str
    user_agent: str = DEFAULT_USER_AGENT
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES


def _validate_token(token: str | None) -> str | None:
    if token is None:
        return None
    if (
        not isinstance(token, str)
        or not token
        or len(token) > 512
        or any(char in _CONTROL_CHARS for char in token)
    ):
        raise ProviderHTTPError("token must be a bounded single-line string")
    return token


def _validate_config(config: ProviderHTTPTransportConfig) -> None:
    if not isinstance(config, ProviderHTTPTransportConfig):
        raise ProviderHTTPError("config must be ProviderHTTPTransportConfig")
    if (
        not isinstance(config.api_base, str)
        or any(char in _CONTROL_CHARS for char in config.api_base)
    ):
        raise ProviderHTTPError("api_base must be an https URL without a trailing slash")
    try:
        parsed = urlsplit(config.api_base)
        hostname = parsed.hostname
    except ValueError:
        parsed, hostname = None, None
    if (
        parsed is None
        or parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or config.api_base.endswith("/")
    ):
        raise ProviderHTTPError("api_base must be an https URL without a trailing slash")
    if (
        not isinstance(config.user_agent, str)
        or not config.user_agent.strip()
        or any(char in _CONTROL_CHARS for char in config.user_agent)
    ):
        raise ProviderHTTPError("user_agent must be a non-empty single-line string")
    if (
        isinstance(config.max_response_bytes, bool)
        or not isinstance(config.max_response_bytes, int)
        or not 1 <= config.max_response_bytes <= DEFAULT_MAX_RESPONSE_BYTES
    ):
        raise ProviderHTTPError("max_response_bytes must be an integer from 1 to 1000000")


def _validate_timeout(timeout: Any) -> None:
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or not 0 < timeout <= DEFAULT_MAX_TIMEOUT_SECONDS
    ):
        raise ProviderHTTPError("HTTP transport timeout must be finite and in (0, 60] seconds")


def _validate_path(provider: str, path: str) -> None:
    if not isinstance(path, str) or len(path) > _MAX_PROVIDER_PATH_LENGTH:
        raise ProviderHTTPError("HTTP transport received a non-whitelisted path")
    pattern = _GITLAB_PATH if provider == "gitlab" else _FORGEJO_PATH
    if provider not in SUPPORTED_ADAPTER_PROVIDERS or not pattern.fullmatch(path):
        raise ProviderHTTPError("HTTP transport received a non-whitelisted path")


def _bounded_headers(response: Any) -> dict[str, str]:
    try:
        raw_headers = getattr(response, "headers", {}) or {}
        return {
            str(key).lower(): value
            for key, value in raw_headers.items()
            if str(key).lower() in _RESPONSE_HEADERS
            and isinstance(value, str)
            and len(value) <= _MAX_RESPONSE_HEADER_VALUE
        }
    except Exception as exc:
        raise ProviderHTTPError("HTTP response headers are invalid") from exc


class ProviderHTTPTransport:
    """Callable GET-only transport for GitLab or Forgejo.

    ``opener`` is injectable so tests and callers can provide a policy-aware
    network implementation.  No redirects are followed by the default opener.
    """

    def __init__(
        self,
        provider: str,
        *,
        token: str | None = None,
        config: ProviderHTTPTransportConfig,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        if provider not in SUPPORTED_ADAPTER_PROVIDERS:
            raise ProviderHTTPError("provider adapter is unsupported")
        _validate_config(config)
        if opener is not None and not callable(opener):
            raise ProviderHTTPError("opener must be callable")
        self.provider = provider
        self.token = _validate_token(token)
        self.config = config
        self.opener = opener or _NO_REDIRECT_OPENER.open

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(provider={self.provider!r}, "
            f"api_base={self.config.api_base!r}, "
            f"user_agent={self.config.user_agent!r}, "
            f"max_response_bytes={self.config.max_response_bytes!r}, "
            f"token_present={self.token is not None!r})"
        )

    @classmethod
    def from_environment(
        cls,
        provider: str,
        *,
        allow_environment: bool = False,
        **kwargs: Any,
    ) -> "ProviderHTTPTransport":
        """Load a provider token only after explicit environment opt-in."""
        token = None
        if allow_environment:
            token = os.environ.get(f"{provider.upper()}_TOKEN")
        return cls(provider, token=token, **kwargs)

    def __call__(
        self, path: str, params: Mapping[str, str], timeout: float
    ) -> TransportResponse:
        _validate_path(self.provider, path)
        if (
            not isinstance(params, Mapping)
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in params.items()
            )
        ):
            raise ProviderHTTPError("HTTP transport parameters must be string pairs")
        _validate_timeout(timeout)
        query = urlencode(sorted(params.items()))
        headers = {
            "Accept": "application/json",
            "User-Agent": self.config.user_agent,
        }
        if self.token:
            headers[
                "PRIVATE-TOKEN" if self.provider == "gitlab" else "Authorization"
            ] = self.token if self.provider == "gitlab" else f"token {self.token}"
        request = Request(
            f"{self.config.api_base}{path}{'?' + query if query else ''}",
            headers=headers,
            method="GET",
        )
        try:
            response = self.opener(request, timeout=float(timeout))
        except HTTPError as exc:
            return self._response(exc.code, exc)
        except (URLError, OSError) as exc:
            raise ProviderHTTPError("HTTP request failed") from exc
        return self._response(getattr(response, "status", 200), response)

    def _response(self, status: Any, response: Any) -> TransportResponse:
        try:
            status_code = int(status)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ProviderHTTPError("HTTP response status is invalid") from exc
        try:
            body = response.read(self.config.max_response_bytes + 1)
        except Exception as exc:
            raise ProviderHTTPError("HTTP response could not be read") from exc
        if not isinstance(body, bytes):
            raise ProviderHTTPError("HTTP response body must be bytes")
        if len(body) > self.config.max_response_bytes:
            body = body[: self.config.max_response_bytes + 1]
        return TransportResponse(status_code, body, _bounded_headers(response))


__all__ = [
    "DEFAULT_MAX_RESPONSE_BYTES",
    "DEFAULT_MAX_TIMEOUT_SECONDS",
    "DEFAULT_USER_AGENT",
    "ProviderHTTPError",
    "ProviderHTTPTransport",
    "ProviderHTTPTransportConfig",
]
