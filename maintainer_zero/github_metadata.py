"""Validate opt-in, read-only GitHub metadata snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 1
_MAX_ITEMS = 5000

class MetadataError(ValueError):
    """Raised when a metadata snapshot violates the local envelope."""

def load_metadata(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MetadataError(f"Invalid GitHub metadata snapshot: {path}") from exc
    return validate_metadata(payload)

def validate_metadata(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise MetadataError("metadata snapshot must be a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise MetadataError(f"unsupported metadata schema_version: {payload.get('schema_version')!r}")
    permissions = payload.get("permissions")
    if not isinstance(permissions, dict) or any(not isinstance(key, str) or not isinstance(value, bool) for key, value in permissions.items()):
        raise MetadataError("metadata permissions must be an object of booleans")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise MetadataError("metadata data must be an object")
    for key in ("issues", "pull_requests", "reviews", "releases"):
        if key in data and (not isinstance(data[key], list) or len(data[key]) > _MAX_ITEMS):
            raise MetadataError(f"metadata {key} must be a bounded array")
    return payload

def summarize_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic summary; unavailable fields remain unknown."""
    validate_metadata(dict(payload))
    permissions = payload["permissions"]
    data = payload["data"]
    summary: dict[str, Any] = {"source": "github-metadata", "read_only": True, "permissions": {key: bool(value) for key, value in sorted(permissions.items())}, "fields": {}, "unknown": []}
    for key in ("issues", "pull_requests", "reviews", "releases"):
        if not permissions.get(key, False) or key not in data:
            summary["fields"][key] = None
            summary["unknown"].append(key)
        else:
            summary["fields"][key] = len(data[key])
    return summary

__all__ = ["MetadataError", "SCHEMA_VERSION", "load_metadata", "summarize_metadata", "validate_metadata"]
