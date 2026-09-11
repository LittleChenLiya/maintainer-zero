"""Validate opt-in, read-only GitHub metadata snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 1
_MAX_ITEMS = 5000
MAX_METADATA_BYTES = 10_000_000
_RESOURCES = ("repository", "issues", "pull_requests", "reviews", "releases")
_ARRAY_RESOURCES = frozenset(_RESOURCES) - {"repository"}

class MetadataError(ValueError):
    """Raised when a metadata snapshot violates the local envelope."""

def load_metadata(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_METADATA_BYTES:
            raise MetadataError(f"metadata snapshot exceeds {MAX_METADATA_BYTES} bytes")
        payload = json.loads(raw)
    except MetadataError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise MetadataError(f"Invalid GitHub metadata snapshot: {path}") from exc
    return validate_metadata(payload)

def validate_metadata(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise MetadataError("metadata snapshot must be a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise MetadataError(f"unsupported metadata schema_version: {payload.get('schema_version')!r}")
    permissions = payload.get("permissions")
    if (not isinstance(permissions, dict) or set(permissions) - set(_RESOURCES)
            or any(not isinstance(key, str) or not isinstance(value, bool) for key, value in permissions.items())):
        raise MetadataError("metadata permissions must be an object of booleans")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise MetadataError("metadata data must be an object")
    if set(data) - set(_RESOURCES):
        raise MetadataError("metadata data contains an unsupported resource")
    if "repository" in data:
        record = data["repository"]
        if not isinstance(record, dict) or len(record) > 32:
            raise MetadataError("metadata repository must be a bounded object")
        allowed = {
            "archived", "default_branch", "fork", "forks_count",
            "has_discussions", "has_issues", "has_wiki",
            "open_issues_count", "stargazers_count", "visibility",
        }
        if set(record) - allowed:
            raise MetadataError("metadata repository contains an unsupported field")
        if any(not isinstance(value, (str, int, float, bool)) and value is not None for value in record.values()):
            raise MetadataError("metadata repository fields must be scalar")
    for key in _ARRAY_RESOURCES:
        if key in data and (not isinstance(data[key], list) or len(data[key]) > _MAX_ITEMS or any(not isinstance(item, dict) for item in data[key])):
            raise MetadataError(f"metadata {key} must be a bounded array")
    collection = payload.get("collection")
    if collection is not None:
        if not isinstance(collection, dict) or set(collection) - set(_RESOURCES):
            raise MetadataError("metadata collection contains an unsupported resource")
        for status in collection.values():
            if not isinstance(status, dict) or not isinstance(status.get("available"), bool):
                raise MetadataError("metadata collection status is malformed")
            pages = status.get("pages")
            if isinstance(pages, bool) or not isinstance(pages, int) or not 0 <= pages <= 50:
                raise MetadataError("metadata collection pages are out of bounds")
            if not isinstance(status.get("truncated"), bool):
                raise MetadataError("metadata collection truncated must be boolean")
    return payload

def summarize_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic summary; unavailable fields remain unknown."""
    validate_metadata(dict(payload))
    permissions = payload["permissions"]
    data = payload["data"]
    summary: dict[str, Any] = {"source": "github-metadata", "read_only": True, "permissions": {key: bool(value) for key, value in sorted(permissions.items())}, "fields": {}, "unknown": []}
    collection = payload.get("collection", {})
    partial: list[str] = []
    for key in _RESOURCES:
        if not permissions.get(key, False) or key not in data:
            summary["fields"][key] = None
            summary["unknown"].append(key)
        else:
            summary["fields"][key] = data[key] if key == "repository" else len(data[key])
        status = collection.get(key) if isinstance(collection, dict) else None
        if isinstance(status, dict) and status.get("truncated") is True:
            partial.append(key)
    if partial:
        summary["partial"] = partial
    return summary

__all__ = ["MAX_METADATA_BYTES", "MetadataError", "SCHEMA_VERSION", "load_metadata", "summarize_metadata", "validate_metadata"]
