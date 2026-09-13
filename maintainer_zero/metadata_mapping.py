"""Offline mapping from bounded provider records to the canonical metadata schema."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .github_metadata import (
    SCHEMA_VERSION,
    SUPPORTED_PROVIDERS,
    MetadataError,
    validate_metadata,
)


# Resource names are intentionally explicit.  This is a data-only mapping, not
# an API client or a permissive key-transformation utility.
_RESOURCE_ALIASES: dict[str, dict[str, str]] = {
    "github": {
        "repository": "repository",
        "issues": "issues",
        "pulls": "pull_requests",
        "pull_requests": "pull_requests",
        "reviews": "reviews",
        "releases": "releases",
    },
    "gitlab": {
        "project": "repository",
        "repository": "repository",
        "issues": "issues",
        "merge_requests": "pull_requests",
        "pull_requests": "pull_requests",
        "reviews": "reviews",
        "releases": "releases",
    },
    "forgejo": {
        "repository": "repository",
        "issues": "issues",
        "pulls": "pull_requests",
        "pull_requests": "pull_requests",
        "reviews": "reviews",
        "releases": "releases",
    },
}

_PERMISSION_ALIASES = _RESOURCE_ALIASES

_FIELD_ALIASES: dict[str, dict[str, dict[str, str]]] = {
    "github": {
        "repository": {
            "default_branch": "default_branch",
            "visibility": "visibility",
            "archived": "archived",
            "fork": "fork",
            "has_issues": "has_issues",
            "has_wiki": "has_wiki",
            "has_discussions": "has_discussions",
            "open_issues_count": "open_issues_count",
            "stargazers_count": "stargazers_count",
            "forks_count": "forks_count",
        },
        "issues": {
            "number": "number", "state": "state", "draft": "draft",
            "created_at": "created_at", "updated_at": "updated_at",
            "closed_at": "closed_at", "comments": "comments",
        },
        "pull_requests": {
            "number": "number", "state": "state", "draft": "draft",
            "created_at": "created_at", "updated_at": "updated_at",
            "closed_at": "closed_at", "merged_at": "merged_at",
            "comments": "comments", "review_comments": "review_comments",
        },
        "reviews": {
            "id": "id", "state": "state", "submitted_at": "submitted_at",
            "commit_id": "commit_id",
        },
        "releases": {
            "id": "id", "draft": "draft", "prerelease": "prerelease",
            "created_at": "created_at", "published_at": "published_at",
        },
    },
    "gitlab": {
        "repository": {
            "default_branch": "default_branch", "visibility": "visibility",
            "archived": "archived", "forked_from_project": "fork",
            "fork": "fork", "issues_enabled": "has_issues",
            "wiki_enabled": "has_wiki", "open_issues_count": "open_issues_count",
            "star_count": "stargazers_count", "forks_count": "forks_count",
        },
        "issues": {
            "iid": "number", "number": "number", "state": "state",
            "created_at": "created_at", "updated_at": "updated_at",
            "closed_at": "closed_at", "user_notes_count": "comments",
            "comments": "comments",
        },
        "pull_requests": {
            "iid": "number", "number": "number", "state": "state",
            "draft": "draft", "created_at": "created_at",
            "updated_at": "updated_at", "closed_at": "closed_at",
            "merged_at": "merged_at", "user_notes_count": "comments",
            "comments": "comments", "review_comments": "review_comments",
        },
        "reviews": {
            "id": "id", "state": "state", "submitted_at": "submitted_at",
            "commit_id": "commit_id",
        },
        "releases": {
            "id": "id", "draft": "draft", "prerelease": "prerelease",
            "created_at": "created_at", "published_at": "published_at",
            # GitLab calls this timestamp `released_at`; normalize it to the
            # provider-neutral `published_at` field.
            "released_at": "published_at",
        },
    },
    "forgejo": {
        "repository": {
            "default_branch": "default_branch", "visibility": "visibility",
            "archived": "archived", "fork": "fork",
            "has_issues": "has_issues", "has_wiki": "has_wiki",
            "has_discussions": "has_discussions", "open_issues_count": "open_issues_count",
            "stars_count": "stargazers_count", "stargazers_count": "stargazers_count",
            "forks_count": "forks_count",
        },
        "issues": {
            "number": "number", "state": "state", "created_at": "created_at",
            "updated_at": "updated_at", "closed_at": "closed_at",
            "comments": "comments",
        },
        "pull_requests": {
            "number": "number", "state": "state", "draft": "draft",
            "created_at": "created_at", "updated_at": "updated_at",
            "closed_at": "closed_at", "merged_at": "merged_at",
            "comments": "comments", "review_comments": "review_comments",
        },
        "reviews": {
            "id": "id", "state": "state", "submitted_at": "submitted_at",
            "commit_id": "commit_id",
        },
        "releases": {
            "id": "id", "draft": "draft", "prerelease": "prerelease",
            "created_at": "created_at", "published_at": "published_at",
        },
    },
}

_TOP_LEVEL_KEYS = frozenset(("schema_version", "provider", "permissions", "data", "collection"))
_STATUS_KEYS = frozenset(("available", "pages", "truncated", "reason", "retry_after_seconds", "rate_limit_reset_epoch"))


def _scalar(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool)):
        return True
    if isinstance(value, int):
        # Provider IDs and counters are bounded machine values; do not let an
        # adapter smuggle arbitrarily large integers into the canonical file.
        return -(1 << 63) <= value <= (1 << 63) - 1
    return isinstance(value, float) and math.isfinite(value)


def _map_resources(provider: str, values: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(values, Mapping):
        raise MetadataError(f"metadata {label} must be an object")
    aliases = _RESOURCE_ALIASES[provider]
    mapped: dict[str, Any] = {}
    for source, value in values.items():
        if not isinstance(source, str) or source not in aliases:
            raise MetadataError(f"metadata {label} contains an unsupported resource")
        target = aliases[source]
        if target in mapped:
            raise MetadataError(f"metadata {label} contains ambiguous resource aliases")
        mapped[target] = value
    return mapped


def _map_record(provider: str, resource: str, record: Any) -> dict[str, Any]:
    aliases = _FIELD_ALIASES[provider][resource]
    if not isinstance(record, Mapping):
        raise MetadataError(f"metadata {resource} records must be objects")
    result: dict[str, Any] = {}
    for source, value in record.items():
        if not isinstance(source, str) or source not in aliases:
            raise MetadataError(f"metadata {resource} contains an unsupported provider field")
        target = aliases[source]
        if target in result:
            raise MetadataError(f"metadata {resource} contains ambiguous field aliases")
        if not _scalar(value):
            raise MetadataError(f"metadata {resource} fields must be scalar")
        result[target] = value
    return {key: result[key] for key in sorted(result)}


def project_provider_record(provider: str, resource: str, record: Mapping[str, Any]) -> dict[str, Any]:
    """Project an API record to the provider-owned input accepted by the mapper.

    Provider APIs return many fields that are outside the continuity contract.
    They are intentionally omitted here; fields that are known to the contract
    must still be scalar.  The stricter :func:`normalize_metadata` call remains
    the final validation boundary.
    """
    if not isinstance(provider, str) or provider not in SUPPORTED_PROVIDERS:
        raise MetadataError("metadata provider is unsupported")
    if not isinstance(resource, str):
        raise MetadataError("metadata resource is unsupported")
    canonical_resource = _RESOURCE_ALIASES[provider].get(resource)
    if canonical_resource is None or canonical_resource not in _FIELD_ALIASES[provider]:
        raise MetadataError("metadata resource is unsupported")
    if not isinstance(record, Mapping):
        raise MetadataError(f"metadata {resource} record must be an object")
    projected: dict[str, Any] = {}
    for source in _FIELD_ALIASES[provider][canonical_resource]:
        if source not in record:
            continue
        value = record[source]
        if not _scalar(value):
            raise MetadataError(f"metadata {resource} fields must be scalar")
        projected[source] = value
    return {key: projected[key] for key in sorted(projected)}


def _map_data(provider: str, data: Any) -> dict[str, Any]:
    mapped = _map_resources(provider, data, label="data")
    result: dict[str, Any] = {}
    for resource, value in mapped.items():
        if resource == "repository":
            result[resource] = _map_record(provider, resource, value)
        else:
            if not isinstance(value, list):
                raise MetadataError(f"metadata {resource} must be an array")
            result[resource] = [_map_record(provider, resource, item) for item in value]
    return result


def _map_collection(provider: str, collection: Any) -> dict[str, Any] | None:
    if collection is None:
        return None
    mapped = _map_resources(provider, collection, label="collection")
    result: dict[str, Any] = {}
    for resource, status in mapped.items():
        if not isinstance(status, Mapping) or set(status) - _STATUS_KEYS:
            raise MetadataError("metadata collection status is malformed")
        result[resource] = dict(status)
    return result


def normalize_metadata(provider: str, raw_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a bounded provider snapshot into the canonical offline envelope.

    The input is an adapter-owned, data-only object.  It is deliberately not an
    HTTP response parser: unknown keys, nested record values, alias collisions,
    credentials, URLs, and identity fields fail closed.
    """
    if not isinstance(provider, str) or provider not in SUPPORTED_PROVIDERS:
        raise MetadataError("metadata provider is unsupported")
    if not isinstance(raw_snapshot, Mapping):
        raise MetadataError("metadata snapshot must be an object")
    if set(raw_snapshot) - _TOP_LEVEL_KEYS:
        raise MetadataError("metadata snapshot contains unsupported adapter fields")
    if "provider" in raw_snapshot and raw_snapshot["provider"] != provider:
        raise MetadataError("metadata provider does not match adapter")
    if raw_snapshot.get("schema_version") != SCHEMA_VERSION:
        raise MetadataError("unsupported metadata schema_version")
    permissions = _map_resources(provider, raw_snapshot.get("permissions"), label="permissions")
    if any(not isinstance(value, bool) for value in permissions.values()):
        raise MetadataError("metadata permissions must be booleans")
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "provider": provider,
        "permissions": permissions,
        "data": _map_data(provider, raw_snapshot.get("data")),
    }
    collection = _map_collection(provider, raw_snapshot.get("collection"))
    if collection is not None:
        result["collection"] = collection
    return validate_metadata(result)


__all__ = ["normalize_metadata", "project_provider_record"]
