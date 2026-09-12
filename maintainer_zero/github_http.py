"""Explicit, bounded stdlib HTTP transport for the read-only GitHub client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .github_client import GitHubClientError, TransportResponse, validate_github_path

DEFAULT_API_BASE = "https://api.github.com"
DEFAULT_USER_AGENT = "maintainer-zero-read-only/0.1"
DEFAULT_MAX_RESPONSE_BYTES = 1_000_000
DEFAULT_MAX_TIMEOUT_SECONDS = 60.0
_CONTROL_CHARS = frozenset(chr(code) for code in range(32)) | {chr(127)}
class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, *args, **kwargs):
        return None


_NO_REDIRECT_OPENER = build_opener(_RejectRedirect)


class GitHubHTTPError(ValueError):
    """Raised when the explicit HTTP transport configuration is unsafe."""


@dataclass(frozen=True)
class HTTPTransportConfig:
    api_base: str = DEFAULT_API_BASE
    user_agent: str = DEFAULT_USER_AGENT
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES


def _validate_token(token: str | None) -> str | None:
    if token is None:
        return None
    if not isinstance(token, str) or not token or len(token) > 512 or any(char in _CONTROL_CHARS for char in token):
        raise GitHubHTTPError("token must be a bounded single-line string")
    return token


class GitHubHTTPTransport:
    """Callable GET-only transport; constructing it never performs network I/O."""

    def __init__(
        self,
        token: str | None = None,
        *,
        config: HTTPTransportConfig = HTTPTransportConfig(),
        opener: Callable[..., Any] | None = None,
    ) -> None:
        try:
            parsed_base = urlsplit(config.api_base) if isinstance(config.api_base, str) else None
            hostname = parsed_base.hostname if parsed_base is not None else None
        except ValueError:
            parsed_base, hostname = None, None
        if (
            parsed_base is None
            or parsed_base.scheme != "https"
            or not hostname
            or parsed_base.username is not None
            or parsed_base.password is not None
            or parsed_base.query
            or parsed_base.fragment
            or config.api_base.endswith("/")
        ):
            raise GitHubHTTPError("api_base must be an https URL without a trailing slash")
        if (not isinstance(config.user_agent, str) or not config.user_agent.strip()
                or any(char in _CONTROL_CHARS for char in config.user_agent)):
            raise GitHubHTTPError("user_agent must be a non-empty single-line string")
        if (isinstance(config.max_response_bytes, bool)
                or not isinstance(config.max_response_bytes, int)
                or not 1 <= config.max_response_bytes <= DEFAULT_MAX_RESPONSE_BYTES):
            raise GitHubHTTPError("max_response_bytes must be an integer from 1 to 1000000")
        if opener is not None and not callable(opener):
            raise GitHubHTTPError("opener must be callable")
        self.token = _validate_token(token)
        self.config = config
        self.opener = opener or _NO_REDIRECT_OPENER.open

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(api_base={self.config.api_base!r}, "
            f"user_agent={self.config.user_agent!r}, "
            f"max_response_bytes={self.config.max_response_bytes!r}, "
            f"token_present={self.token is not None!r})"
        )

    @classmethod
    def from_environment(cls, *, allow_environment: bool = False, **kwargs: Any) -> "GitHubHTTPTransport":
        """Opt-in environment token loading; no environment is read by default."""
        if not allow_environment:
            return cls(**kwargs)
        import os

        return cls(os.environ.get("GITHUB_TOKEN"), **kwargs)

    def __call__(self, path: str, params: Mapping[str, str], timeout: float) -> TransportResponse:
        try:
            validate_github_path(path)
        except GitHubClientError as exc:
            raise GitHubHTTPError("HTTP transport received a non-whitelisted path") from exc
        if not isinstance(params, Mapping) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in params.items()):
            raise GitHubHTTPError("HTTP transport parameters must be string pairs")
        if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                or not 0 < timeout <= DEFAULT_MAX_TIMEOUT_SECONDS):
            raise GitHubHTTPError("HTTP transport timeout must be finite and in (0, 60] seconds")
        query = urlencode(sorted(params.items()))
        request = Request(
            f"{self.config.api_base}{path}{'?' + query if query else ''}",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": self.config.user_agent,
                **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
            },
            method="GET",
        )
        try:
            response = self.opener(request, timeout=float(timeout))
        except HTTPError as exc:
            return self._response(exc.code, exc)
        except URLError:
            raise
        return self._response(getattr(response, "status", 200), response)

    def _response(self, status: int, response: Any) -> TransportResponse:
        body = response.read(self.config.max_response_bytes + 1)
        if not isinstance(body, bytes):
            body = bytes(body)
        if len(body) > self.config.max_response_bytes:
            body = body[: self.config.max_response_bytes + 1]
        headers = {str(key): str(value) for key, value in getattr(response, "headers", {}).items()}
        return TransportResponse(int(status), body, headers)


__all__ = ["DEFAULT_API_BASE", "GitHubHTTPError", "GitHubHTTPTransport", "HTTPTransportConfig"]
