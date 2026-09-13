"""Injected, read-only provider adapters for GitLab and Forgejo metadata."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Mapping
from typing import Any

from .github_client import TransportResponse
from .github_metadata import MAX_METADATA_BYTES, MAX_METADATA_NESTING, SCHEMA_VERSION, MetadataError
from .metadata_mapping import normalize_metadata, project_provider_record

SUPPORTED_ADAPTER_PROVIDERS = ("gitlab", "forgejo")
DEFAULT_MAX_PAGES = 5
DEFAULT_PAGE_SIZE = 100
DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_COLLECTION_ITEMS = 5000
MAX_COLLECTION_BYTES = MAX_METADATA_BYTES
_MAX_TIMEOUT_SECONDS = 60.0
_MAX_PAGES = 50
_MAX_PAGE_SIZE = 100
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
_CONTROL_CHARS = frozenset(chr(code) for code in range(32)) | {chr(127)}


class ProviderClientError(ValueError):
    """Raised for unsafe adapter configuration or provider path input."""


def _validate_bounds(timeout_seconds: Any, max_pages: Any, page_size: Any, max_response_bytes: Any) -> None:
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= _MAX_TIMEOUT_SECONDS):
        raise ProviderClientError("timeout must be finite and in (0, 60] seconds")
    for name, value, maximum in (("max_pages", max_pages, _MAX_PAGES), ("page_size", page_size, _MAX_PAGE_SIZE)):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
            raise ProviderClientError(f"{name} must be an integer from 1 to {maximum}")
    if (isinstance(max_response_bytes, bool) or not isinstance(max_response_bytes, int)
            or not 1 <= max_response_bytes <= MAX_METADATA_BYTES):
        raise ProviderClientError(f"max_response_bytes must be an integer from 1 to {MAX_METADATA_BYTES}")


def validate_provider_identifier(provider: str, identifier: str) -> str:
    if provider == "gitlab":
        if not isinstance(identifier, str) or not re.fullmatch(r"[1-9][0-9]{0,9}", identifier):
            raise ProviderClientError("gitlab identifier must be a numeric project id")
        return identifier
    if provider == "forgejo":
        if not isinstance(identifier, str) or not _SLUG.fullmatch(identifier):
            raise ProviderClientError("forgejo identifier must use OWNER/REPOSITORY format")
        return identifier
    raise ProviderClientError("provider adapter is unsupported")


def provider_paths(provider: str, identifier: str, *, include_repository: bool = False, reviews_pr: int | None = None) -> dict[str, str]:
    """Build an explicit provider endpoint allowlist; no arbitrary paths are accepted."""
    identifier = validate_provider_identifier(provider, identifier)
    if reviews_pr is not None and (isinstance(reviews_pr, bool) or not isinstance(reviews_pr, int)
                                   or not 1 <= reviews_pr <= 9_999_999_999):
        raise ProviderClientError("reviews_pr must be an integer from 1 to 9999999999")
    if provider == "gitlab":
        prefix = f"/api/v4/projects/{identifier}"
        paths = {"issues": f"{prefix}/issues", "merge_requests": f"{prefix}/merge_requests", "releases": f"{prefix}/releases"}
        if include_repository:
            paths = {"project": prefix, **paths}
        if reviews_pr is not None:
            raise ProviderClientError("gitlab reviews are not supported by the data-only adapter")
        return paths
    prefix = f"/api/v1/repos/{identifier}"
    paths = {"issues": f"{prefix}/issues", "pulls": f"{prefix}/pulls", "releases": f"{prefix}/releases"}
    if include_repository:
        paths = {"repository": prefix, **paths}
    if reviews_pr is not None:
        paths["reviews"] = f"{prefix}/pulls/{reviews_pr}/reviews"
    return paths


def _reject_number(value: str) -> None:
    raise ValueError(f"non-standard JSON number: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _validate_response_shape(value: Any, *, depth: int = 0, active: set[int] | None = None) -> None:
    if depth > MAX_METADATA_NESTING:
        raise ValueError("response nesting exceeds limit")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("response contains a non-finite number")
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
            _validate_response_shape(item, depth=depth + 1, active=active)
    finally:
        active.remove(identity)


def _header(headers: Mapping[str, str] | None, name: str) -> str | None:
    for key, value in (headers or {}).items():
        if str(key).lower() == name.lower():
            return str(value)
    return None


def _has_next(headers: Mapping[str, str] | None) -> bool:
    return bool(re.search(r'<[^>]+>;\s*rel="next"', _header(headers, "link") or "", re.I))


def _rate_limit_hints(headers: Mapping[str, str] | None) -> tuple[int | None, int | None]:
    retry_after = _header(headers, "retry-after") or ""
    reset = _header(headers, "x-ratelimit-reset") or ""
    # Check length before int() so hostile digit strings cannot trigger costly
    # conversion or interpreter limits while handling a rate-limited response.
    retry = int(retry_after) if retry_after.isdigit() and len(retry_after) <= 5 and int(retry_after) <= 86_400 else None
    epoch = int(reset) if reset.isdigit() and len(reset) <= 10 and int(reset) <= 4_102_444_800 else None
    return retry, epoch


def _status(available: bool, pages: int, truncated: bool, reason: str | None = None, headers: Mapping[str, str] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"available": available, "pages": pages, "truncated": truncated}
    if reason:
        payload["reason"] = reason
    retry, epoch = _rate_limit_hints(headers)
    if retry is not None:
        payload["retry_after_seconds"] = retry
    if epoch is not None:
        payload["rate_limit_reset_epoch"] = epoch
    return payload


class ReadOnlyProviderClient:
    """Collect bounded GitLab/Forgejo metadata through an injected GET transport."""

    def __init__(self, provider: str, fetch: Callable[[str, Mapping[str, str], float], TransportResponse], *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS, max_pages: int = DEFAULT_MAX_PAGES, page_size: int = DEFAULT_PAGE_SIZE, max_response_bytes: int = 1_000_000) -> None:
        if provider not in SUPPORTED_ADAPTER_PROVIDERS:
            raise ProviderClientError("provider adapter is unsupported")
        _validate_bounds(timeout_seconds, max_pages, page_size, max_response_bytes)
        if not callable(fetch):
            raise ProviderClientError("fetch must be callable")
        self.provider = provider
        self.fetch = fetch
        self.timeout_seconds = float(timeout_seconds)
        self.max_pages = max_pages
        self.page_size = page_size
        self.max_response_bytes = max_response_bytes

    def collect(self, identifier: str, *, include_repository: bool = False, reviews_pr: int | None = None) -> dict[str, Any]:
        paths = provider_paths(self.provider, identifier, include_repository=include_repository, reviews_pr=reviews_pr)
        data: dict[str, Any] = {}
        permissions: dict[str, bool] = {}
        collection: dict[str, dict[str, Any]] = {}
        for source, path in paths.items():
            canonical = {"merge_requests": "pull_requests", "pulls": "pull_requests", "project": "repository", "repository": "repository"}.get(source, source)
            if canonical == "repository":
                record, status = self._collect_object(source, path)
            else:
                record, status = self._collect_array(source, path)
            permissions[source] = status["available"]
            collection[source] = status
            if status["available"]:
                data[source] = record
        return normalize_metadata(self.provider, {"schema_version": SCHEMA_VERSION, "provider": self.provider, "permissions": permissions, "data": data, "collection": collection})

    def _call(self, path: str, params: Mapping[str, str]) -> TransportResponse | None:
        try:
            response = self.fetch(path, params, self.timeout_seconds)
        except Exception:
            return None
        return response if isinstance(response, TransportResponse) else None

    def _decode(self, response: TransportResponse) -> Any:
        raw = response.body.encode("utf-8") if isinstance(response.body, str) else response.body
        if not isinstance(raw, bytes) or len(raw) > self.max_response_bytes:
            raise ValueError("response too large")
        payload = json.loads(raw, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_number)
        _validate_response_shape(payload)
        return payload

    def _unavailable(self, response: TransportResponse | None, pages: int, reason: str) -> tuple[dict[str, Any], dict[str, Any]]:
        status_code = response.status_code if response is not None else None
        if status_code in (401, 403, 404, 429):
            reason = {401: "unauthorized", 403: "forbidden_or_rate_limited", 404: "not_found_or_unavailable", 429: "rate_limited"}[status_code]
        return {}, _status(False, pages, False, reason, response.headers if response is not None else None)

    def _collect_object(self, source: str, path: str) -> tuple[dict[str, Any], dict[str, Any]]:
        response = self._call(path, {})
        if response is None:
            return self._unavailable(response, 0, "transport_error")
        if response.status_code != 200:
            return self._unavailable(response, 1, f"http_{response.status_code}")
        try:
            payload = self._decode(response)
            if not isinstance(payload, dict):
                raise ValueError("expected object")
            return project_provider_record(self.provider, source, payload), _status(True, 1, False)
        except (MetadataError, ValueError, TypeError, UnicodeError, json.JSONDecodeError, RecursionError):
            return self._unavailable(response, 1, "invalid_json")

    def _collect_array(self, source: str, path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        records: list[dict[str, Any]] = []
        total_bytes = 0
        # GitLab uses per_page while Forgejo/Gitea uses limit. Keep the
        # provider-specific spelling so an ignored parameter cannot silently
        # change page sizes and invalidate truncation semantics.
        page_size_key = "per_page" if self.provider == "gitlab" else "limit"
        for page in range(1, self.max_pages + 1):
            response = self._call(path, {"page": str(page), page_size_key: str(self.page_size)})
            if response is None:
                return [], _status(False, page - 1, False, "transport_error")
            if response.status_code != 200:
                if response.status_code in (401, 403, 404, 429):
                    reason = {
                        401: "unauthorized",
                        403: "forbidden_or_rate_limited",
                        404: "not_found_or_unavailable",
                        429: "rate_limited",
                    }[response.status_code]
                else:
                    reason = f"http_{response.status_code}"
                return [], _status(False, page - 1, False, reason, response.headers)
            try:
                raw = response.body.encode("utf-8") if isinstance(response.body, str) else response.body
                if not isinstance(raw, bytes) or len(raw) > self.max_response_bytes:
                    raise ValueError("response too large")
                total_bytes += len(raw)
                if total_bytes > MAX_COLLECTION_BYTES:
                    raise ValueError("collection too large")
                payload = json.loads(raw, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_number)
                _validate_response_shape(payload)
                if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
                    raise ValueError("expected array of objects")
                projected = [project_provider_record(self.provider, source, item) for item in payload]
            except (MetadataError, ValueError, TypeError, UnicodeError, json.JSONDecodeError, RecursionError):
                return [], _status(False, page, False, "invalid_json", response.headers)
            if len(records) + len(projected) > MAX_COLLECTION_ITEMS:
                records.extend(projected[: MAX_COLLECTION_ITEMS - len(records)])
                return records, _status(True, page, True, "item_limit")
            records.extend(projected)
            if len(payload) < self.page_size and not _has_next(response.headers):
                return records, _status(True, page, False)
        return records, _status(True, self.max_pages, True, "page_limit")


__all__ = ["DEFAULT_MAX_PAGES", "DEFAULT_PAGE_SIZE", "DEFAULT_TIMEOUT_SECONDS", "ProviderClientError", "ReadOnlyProviderClient", "SUPPORTED_ADAPTER_PROVIDERS", "provider_paths", "validate_provider_identifier"]
