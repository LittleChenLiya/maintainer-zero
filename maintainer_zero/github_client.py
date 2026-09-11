"""Bounded, read-only GitHub metadata collection with injected transport."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .github_metadata import SCHEMA_VERSION, validate_metadata

MAX_COLLECTION_ITEMS = 5000
DEFAULT_MAX_PAGES = 5
DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_RESPONSE_BYTES = 1_000_000
DEFAULT_TIMEOUT_SECONDS = 5.0
_PATHS = {
    "issues": re.compile(r"^/repos/[^/]+/[^/]+/issues$"),
    "pull_requests": re.compile(r"^/repos/[^/]+/[^/]+/pulls$"),
    "reviews": re.compile(r"^/repos/[^/]+/[^/]+/pulls/[1-9][0-9]*/reviews$"),
    "releases": re.compile(r"^/repos/[^/]+/[^/]+/releases$"),
}

@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    body: bytes | str
    headers: Mapping[str, str] | None = None

@dataclass(frozen=True)
class CollectionStatus:
    available: bool
    pages: int
    truncated: bool
    reason: str | None = None

class GitHubClientError(ValueError):
    """Raised for invalid bounds or non-whitelisted paths."""

def _header(headers: Mapping[str, str] | None, name: str) -> str | None:
    for key, value in (headers or {}).items():
        if str(key).lower() == name.lower():
            return str(value)
    return None

def _has_next(headers: Mapping[str, str] | None) -> bool:
    return bool(re.search(r'<[^>]+>;\s*rel="next"', _header(headers, "link") or "", re.I))

class ReadOnlyGitHubClient:
    """Collect bounded metadata through a caller-owned GET-only transport."""

    def __init__(self, fetch: Callable[[str, Mapping[str, str], float], TransportResponse], *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS, max_pages: int = DEFAULT_MAX_PAGES, page_size: int = DEFAULT_PAGE_SIZE, max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES) -> None:
        if timeout_seconds <= 0 or max_pages < 1 or not 1 <= page_size <= 100 or max_response_bytes < 1:
            raise GitHubClientError("invalid client bounds")
        self.fetch, self.timeout_seconds = fetch, float(timeout_seconds)
        self.max_pages, self.page_size, self.max_response_bytes = int(max_pages), int(page_size), int(max_response_bytes)

    def collect(self, paths: Mapping[str, str]) -> dict[str, Any]:
        data: dict[str, list[Any]] = {}
        permissions: dict[str, bool] = {}
        collection: dict[str, dict[str, Any]] = {}
        for resource, path in sorted(paths.items()):
            if resource not in _PATHS or not _PATHS[resource].match(path):
                raise GitHubClientError(f"unsupported metadata path for {resource!r}")
            records, status = self._collect_resource(path)
            permissions[resource] = status.available
            collection[resource] = {"available": status.available, "pages": status.pages, "truncated": status.truncated, **({"reason": status.reason} if status.reason else {})}
            if status.available:
                data[resource] = records
        return validate_metadata({"schema_version": SCHEMA_VERSION, "permissions": permissions, "data": data, "collection": collection})

    def _collect_resource(self, path: str) -> tuple[list[Any], CollectionStatus]:
        records: list[Any] = []
        for page in range(1, self.max_pages + 1):
            try:
                response = self.fetch(path, {"page": str(page), "per_page": str(self.page_size)}, self.timeout_seconds)
            except Exception:
                return records, CollectionStatus(False, page - 1, False, "transport_error")
            if not isinstance(response, TransportResponse):
                return records, CollectionStatus(False, page - 1, False, "invalid_transport_response")
            if response.status_code in (401, 403, 404, 429):
                reasons = {401: "unauthorized", 403: "forbidden_or_rate_limited", 404: "not_found_or_unavailable", 429: "rate_limited"}
                return records, CollectionStatus(False, page - 1, False, reasons[response.status_code])
            if response.status_code != 200:
                return records, CollectionStatus(False, page - 1, False, f"http_{response.status_code}")
            raw = response.body.encode("utf-8") if isinstance(response.body, str) else response.body
            if not isinstance(raw, bytes) or len(raw) > self.max_response_bytes:
                return records, CollectionStatus(False, page, False, "response_too_large")
            try:
                payload = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                return records, CollectionStatus(False, page, False, "invalid_json")
            if not isinstance(payload, list):
                return records, CollectionStatus(False, page, False, "expected_array")
            if len(records) + len(payload) > MAX_COLLECTION_ITEMS:
                return records[:MAX_COLLECTION_ITEMS], CollectionStatus(True, page, True, "item_limit")
            records.extend(payload)
            if len(payload) < self.page_size and not _has_next(response.headers):
                return records, CollectionStatus(True, page, False)
        return records, CollectionStatus(True, self.max_pages, True, "page_limit")

__all__ = ["CollectionStatus", "GitHubClientError", "ReadOnlyGitHubClient", "TransportResponse"]
