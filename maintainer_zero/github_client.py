"""Bounded, read-only GitHub metadata collection with injected transport."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .github_metadata import SCHEMA_VERSION, validate_metadata

MAX_COLLECTION_ITEMS = 5000
DEFAULT_MAX_PAGES = 5
DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_RESPONSE_BYTES = 1_000_000
DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_COLLECTION_BYTES = 10_000_000
MAX_RESPONSE_NESTING = 64
_REPOSITORY_PATH = r"/repos/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}"
_PATHS = {
    "repository": re.compile(_REPOSITORY_PATH),
    "issues": re.compile(_REPOSITORY_PATH + r"/issues"),
    "pull_requests": re.compile(_REPOSITORY_PATH + r"/pulls"),
    "reviews": re.compile(_REPOSITORY_PATH + r"/pulls/[1-9][0-9]{0,9}/reviews"),
    "releases": re.compile(_REPOSITORY_PATH + r"/releases"),
}
_ARRAY_RESOURCES = frozenset(("issues", "pull_requests", "reviews", "releases"))
_RESOURCE_FIELDS = {
    "issues": frozenset(("number", "state", "draft", "created_at", "updated_at", "closed_at", "comments")),
    "pull_requests": frozenset(("number", "state", "draft", "created_at", "updated_at", "closed_at", "merged_at", "comments", "review_comments")),
    "reviews": frozenset(("id", "state", "submitted_at", "commit_id")),
    "releases": frozenset(("id", "draft", "prerelease", "created_at", "published_at")),
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
    retry_after_seconds: int | None = None
    rate_limit_reset_epoch: int | None = None

class GitHubClientError(ValueError):
    """Raised for invalid bounds or non-whitelisted paths."""


def _reject_nonstandard_number(value: str) -> None:
    raise ValueError(f"non-standard JSON number: {value}")


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject ambiguous provider responses instead of keeping the last key."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _validate_response_values(value: Any, *, depth: int = 0, active: set[int] | None = None) -> None:
    """Reject cyclic, deeply nested, non-finite, or unbounded values."""
    if depth > MAX_RESPONSE_NESTING:
        raise ValueError(f"response nesting exceeds {MAX_RESPONSE_NESTING} levels")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("response contains a non-finite number")
    if isinstance(value, int) and not isinstance(value, bool) and not -(1 << 63) <= value <= (1 << 63) - 1:
        raise ValueError("response contains an unbounded integer")
    if not isinstance(value, (dict, list)):
        return
    active = active or set()
    identity = id(value)
    if identity in active:
        raise ValueError("response contains a cyclic structure")
    active.add(identity)
    try:
        nested = value.values() if isinstance(value, dict) else value
        for item in nested:
            _validate_response_values(item, depth=depth + 1, active=active)
    finally:
        active.remove(identity)


def _contains_non_finite_number(value: Any, *, depth: int = 0, active: set[int] | None = None) -> bool:
    if depth > MAX_RESPONSE_NESTING:
        raise ValueError(f"response nesting exceeds {MAX_RESPONSE_NESTING} levels")
    if active is None:
        active = set()
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, (dict, list)):
        identity = id(value)
        if identity in active:
            raise ValueError("response contains a cyclic structure")
        active.add(identity)
        try:
            nested = value.values() if isinstance(value, dict) else value
            return any(_contains_non_finite_number(item, depth=depth + 1, active=active) for item in nested)
        finally:
            active.remove(identity)
    return False


def validate_github_path(path: str) -> None:
    if not isinstance(path, str) or not any(pattern.fullmatch(path) for pattern in _PATHS.values()):
        raise GitHubClientError("unsupported metadata path")


def validate_client_bounds(timeout_seconds, max_pages, page_size, max_response_bytes) -> None:
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not 0 < timeout_seconds <= 60 or not math.isfinite(timeout_seconds)):
        raise GitHubClientError("timeout must be finite and in (0, 60] seconds")
    for name, value, maximum in (
        ("max_pages", max_pages, 50), ("page_size", page_size, 100),
        ("max_response_bytes", max_response_bytes, DEFAULT_MAX_RESPONSE_BYTES),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
            raise GitHubClientError(f"{name} must be an integer from 1 to {maximum}")

def _header(headers: Mapping[str, str] | None, name: str) -> str | None:
    for key, value in (headers or {}).items():
        if str(key).lower() == name.lower():
            return str(value)
    return None

def _has_next(headers: Mapping[str, str] | None) -> bool:
    return bool(re.search(r'<[^>]+>;\s*rel="next"', _header(headers, "link") or "", re.I))

def _rate_limit_hints(headers: Mapping[str, str] | None) -> tuple[int | None, int | None]:
    """Extract bounded scheduling hints without preserving arbitrary headers."""
    retry_after: int | None = None
    reset_epoch: int | None = None
    raw_retry = (_header(headers, "retry-after") or "").strip()
    if raw_retry.isdigit():
        value = int(raw_retry)
        if value <= 86_400:
            retry_after = value
    raw_reset = (_header(headers, "x-ratelimit-reset") or "").strip()
    if raw_reset.isdigit():
        value = int(raw_reset)
        if 0 <= value <= 4_102_444_800:
            reset_epoch = value
    return retry_after, reset_epoch

def _status_payload(status: CollectionStatus) -> dict[str, Any]:
    payload: dict[str, Any] = {"available": status.available, "pages": status.pages, "truncated": status.truncated}
    if status.reason:
        payload["reason"] = status.reason
    if status.retry_after_seconds is not None:
        payload["retry_after_seconds"] = status.retry_after_seconds
    if status.rate_limit_reset_epoch is not None:
        payload["rate_limit_reset_epoch"] = status.rate_limit_reset_epoch
    return payload


def _project_record(resource: str, record: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only bounded, data-only fields needed for continuity counts."""
    allowed = _RESOURCE_FIELDS[resource]
    projected: dict[str, Any] = {}
    for key in sorted(allowed):
        value = record.get(key)
        if value is None or isinstance(value, (str, int, float, bool)):
            if key in record:
                projected[key] = value
    return projected

class ReadOnlyGitHubClient:
    """Collect bounded metadata through a caller-owned GET-only transport."""

    def __init__(self, fetch: Callable[[str, Mapping[str, str], float], TransportResponse], *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS, max_pages: int = DEFAULT_MAX_PAGES, page_size: int = DEFAULT_PAGE_SIZE, max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES) -> None:
        validate_client_bounds(timeout_seconds, max_pages, page_size, max_response_bytes)
        if not callable(fetch):
            raise GitHubClientError("fetch must be callable")
        self.fetch, self.timeout_seconds = fetch, float(timeout_seconds)
        self.max_pages, self.page_size, self.max_response_bytes = int(max_pages), int(page_size), int(max_response_bytes)

    def collect(self, paths: Mapping[str, str]) -> dict[str, Any]:
        # Validate the entire request before any resource starts network I/O.
        if not isinstance(paths, Mapping) or not 1 <= len(paths) <= len(_PATHS):
            raise GitHubClientError(f"paths must contain 1..{len(_PATHS)} supported resources")
        for resource, path in paths.items():
            if (not isinstance(resource, str) or resource not in _PATHS
                    or not isinstance(path, str) or not _PATHS[resource].fullmatch(path)):
                raise GitHubClientError("unsupported metadata path or resource")
        data: dict[str, list[Any]] = {}
        permissions: dict[str, bool] = {}
        collection: dict[str, dict[str, Any]] = {}
        for resource, path in sorted(paths.items()):
            records, status = (self._collect_resource(resource, path) if resource in _ARRAY_RESOURCES else self._collect_repository(path))
            permissions[resource] = status.available
            collection[resource] = _status_payload(status)
            if status.available:
                data[resource] = records
        return validate_metadata({"schema_version": SCHEMA_VERSION, "provider": "github", "permissions": permissions, "data": data, "collection": collection})

    def _collect_repository(self, path: str) -> tuple[dict[str, Any], CollectionStatus]:
        """Fetch one repository descriptor and keep only safe scalar fields."""
        try:
            response = self.fetch(path, {}, self.timeout_seconds)
        except Exception:
            return {}, CollectionStatus(False, 0, False, "transport_error")
        if not isinstance(response, TransportResponse):
            return {}, CollectionStatus(False, 0, False, "invalid_transport_response")
        if response.status_code in (401, 403, 404, 429):
            reasons = {401: "unauthorized", 403: "forbidden_or_rate_limited", 404: "not_found_or_unavailable", 429: "rate_limited"}
            retry_after, reset_epoch = _rate_limit_hints(response.headers)
            return {}, CollectionStatus(False, 0, False, reasons[response.status_code], retry_after, reset_epoch)
        if response.status_code != 200:
            return {}, CollectionStatus(False, 0, False, f"http_{response.status_code}")
        try:
            raw = response.body.encode("utf-8") if isinstance(response.body, str) else response.body
        except UnicodeError:
            return {}, CollectionStatus(False, 1, False, "invalid_json")
        if not isinstance(raw, bytes) or len(raw) > self.max_response_bytes:
            return {}, CollectionStatus(False, 1, False, "response_too_large")
        try:
            payload = json.loads(raw, object_pairs_hook=_reject_duplicate_object_keys, parse_constant=_reject_nonstandard_number)
            _validate_response_values(payload)
        except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError):
            return {}, CollectionStatus(False, 1, False, "invalid_json")
        try:
            invalid_number = _contains_non_finite_number(payload)
        except (ValueError, RecursionError):
            return {}, CollectionStatus(False, 1, False, "invalid_json")
        if invalid_number:
            return {}, CollectionStatus(False, 1, False, "invalid_json")
        if not isinstance(payload, dict):
            return {}, CollectionStatus(False, 1, False, "expected_object")
        allowed = {
            "default_branch", "visibility", "archived", "fork",
            "has_issues", "has_wiki", "has_discussions",
            "open_issues_count", "stargazers_count", "forks_count",
        }
        record = {key: payload[key] for key in sorted(allowed) if key in payload}
        if any(not isinstance(value, (str, int, float, bool)) and value is not None for value in record.values()):
            return {}, CollectionStatus(False, 1, False, "invalid_record")
        return record, CollectionStatus(True, 1, False)

    def _collect_resource(self, resource: str, path: str) -> tuple[list[Any], CollectionStatus]:
        records: list[Any] = []
        collected_bytes = 0
        for page in range(1, self.max_pages + 1):
            try:
                response = self.fetch(path, {"page": str(page), "per_page": str(self.page_size)}, self.timeout_seconds)
            except Exception:
                return records, CollectionStatus(False, page - 1, False, "transport_error")
            if not isinstance(response, TransportResponse):
                return records, CollectionStatus(False, page - 1, False, "invalid_transport_response")
            if response.status_code in (401, 403, 404, 429):
                reasons = {401: "unauthorized", 403: "forbidden_or_rate_limited", 404: "not_found_or_unavailable", 429: "rate_limited"}
                retry_after, reset_epoch = _rate_limit_hints(response.headers)
                return records, CollectionStatus(False, page - 1, False, reasons[response.status_code], retry_after, reset_epoch)
            if response.status_code != 200:
                return records, CollectionStatus(False, page - 1, False, f"http_{response.status_code}")
            try:
                raw = response.body.encode("utf-8") if isinstance(response.body, str) else response.body
            except UnicodeError:
                return records, CollectionStatus(False, page, False, "invalid_json")
            if not isinstance(raw, bytes) or len(raw) > self.max_response_bytes:
                return records, CollectionStatus(False, page, False, "response_too_large")
            collected_bytes += len(raw)
            if collected_bytes > MAX_COLLECTION_BYTES:
                return records, CollectionStatus(False, page, False, "collection_too_large")
            try:
                payload = json.loads(raw, object_pairs_hook=_reject_duplicate_object_keys, parse_constant=_reject_nonstandard_number)
                _validate_response_values(payload)
            except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError):
                return records, CollectionStatus(False, page, False, "invalid_json")
            try:
                invalid_number = _contains_non_finite_number(payload)
            except (ValueError, RecursionError):
                return records, CollectionStatus(False, page, False, "invalid_json")
            if invalid_number:
                return records, CollectionStatus(False, page, False, "invalid_json")
            if not isinstance(payload, list):
                return records, CollectionStatus(False, page, False, "expected_array")
            if any(not isinstance(record, dict) for record in payload):
                return records, CollectionStatus(False, page, False, "invalid_record")
            payload = [_project_record(resource, record) for record in payload]
            if len(records) + len(payload) > MAX_COLLECTION_ITEMS:
                records.extend(payload[:MAX_COLLECTION_ITEMS - len(records)])
                return records, CollectionStatus(True, page, True, "item_limit")
            records.extend(payload)
            if len(payload) < self.page_size and not _has_next(response.headers):
                return records, CollectionStatus(True, page, False)
        return records, CollectionStatus(True, self.max_pages, True, "page_limit")

__all__ = ["CollectionStatus", "GitHubClientError", "ReadOnlyGitHubClient", "TransportResponse"]
