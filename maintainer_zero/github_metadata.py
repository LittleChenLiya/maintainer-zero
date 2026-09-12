"""Validate opt-in, read-only GitHub metadata snapshots."""

from __future__ import annotations

import json
import math
import os
import stat
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 1
_MAX_ITEMS = 5000
MAX_METADATA_BYTES = 10_000_000
MAX_METADATA_NESTING = 64
_RESOURCES = ("repository", "issues", "pull_requests", "reviews", "releases")
_ARRAY_RESOURCES = frozenset(_RESOURCES) - {"repository"}
_RESOURCE_FIELDS = {
    "issues": frozenset(("number", "state", "draft", "created_at", "updated_at", "closed_at", "comments")),
    "pull_requests": frozenset(("number", "state", "draft", "created_at", "updated_at", "closed_at", "merged_at", "comments", "review_comments")),
    "reviews": frozenset(("id", "state", "submitted_at", "commit_id")),
    "releases": frozenset(("id", "draft", "prerelease", "created_at", "published_at")),
}
_TOP_LEVEL_KEYS = frozenset(("schema_version", "permissions", "data", "collection", "cache"))

class MetadataError(ValueError):
    """Raised when a metadata snapshot violates the local envelope."""


def _is_link_like(info: os.stat_result) -> bool:
    """Treat Windows junctions/reparse points as links as well as POSIX symlinks."""
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & reparse_flag)


def _reject_symlinked_parents(path: Path) -> Path:
    """Return an absolute path after checking existing parent components."""
    target = Path(path)
    if not target.is_absolute():
        target = Path.cwd() / target
    current = Path(target.anchor) if target.anchor else Path()
    parts = target.parts[1:] if target.anchor else target.parts
    for part in parts[:-1]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise MetadataError(f"could not inspect metadata snapshot path: {current}") from exc
        if _is_link_like(info):
            raise MetadataError("metadata snapshot path may not contain a symlink or reparse point")
        if not stat.S_ISDIR(info.st_mode):
            raise MetadataError("metadata snapshot parent must be a directory")
    return target


def _open_snapshot(path: Path):
    """Open a snapshot without following links or accepting special files."""
    path = _reject_symlinked_parents(path)
    try:
        path_stat = path.lstat()
        if _is_link_like(path_stat) or not stat.S_ISREG(path_stat.st_mode):
            raise MetadataError("metadata snapshot must be a regular file")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            os.close(descriptor)
            raise MetadataError("metadata snapshot must be a regular file")
        if (getattr(path_stat, "st_dev", 0), getattr(path_stat, "st_ino", 0)) != (
            getattr(file_stat, "st_dev", 0), getattr(file_stat, "st_ino", 0)
        ):
            os.close(descriptor)
            raise MetadataError("metadata snapshot changed during open")
        return os.fdopen(descriptor, "rb")
    except MetadataError:
        raise
    except OSError as exc:
        raise MetadataError(f"Invalid GitHub metadata snapshot: {path}") from exc


def _reject_nonstandard_number(value: str) -> None:
    raise MetadataError(f"metadata contains non-standard JSON number: {value}")


def _validate_finite_numbers(value: Any, *, depth: int = 0, active: set[int] | None = None) -> None:
    if active is None:
        active = set()
    if depth > MAX_METADATA_NESTING:
        raise MetadataError(f"metadata nesting exceeds {MAX_METADATA_NESTING} levels")
    if isinstance(value, float) and not math.isfinite(value):
        raise MetadataError("metadata contains a non-finite number")
    if not isinstance(value, (dict, list)):
        return
    identity = id(value)
    if identity in active:
        raise MetadataError("metadata contains a cyclic structure")
    active.add(identity)
    try:
        nested_values = value.values() if isinstance(value, dict) else value
        for nested in nested_values:
            _validate_finite_numbers(nested, depth=depth + 1, active=active)
    finally:
        active.remove(identity)

def load_metadata(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    try:
        with _open_snapshot(path) as handle:
            raw = handle.read(MAX_METADATA_BYTES + 1)
        if len(raw) > MAX_METADATA_BYTES:
            raise MetadataError(f"metadata snapshot exceeds {MAX_METADATA_BYTES} bytes")
        payload = json.loads(raw, parse_constant=_reject_nonstandard_number)
    except MetadataError:
        raise
    except (OSError, json.JSONDecodeError, RecursionError) as exc:
        raise MetadataError(f"Invalid GitHub metadata snapshot: {path}") from exc
    return validate_metadata(payload)

def validate_metadata(payload: Any) -> dict[str, Any]:
    _validate_finite_numbers(payload)
    if not isinstance(payload, dict):
        raise MetadataError("metadata snapshot must be a JSON object")
    if set(payload) - _TOP_LEVEL_KEYS:
        raise MetadataError("metadata snapshot contains unsupported top-level fields")
    if "cache" in payload:
        cache = payload["cache"]
        if not isinstance(cache, dict) or set(cache) != {"schema_version", "source", "fetched_at", "expires_at", "ttl_seconds"}:
            raise MetadataError("metadata cache envelope is malformed")
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
        records = data.get(key)
        if key not in data:
            continue
        if not isinstance(records, list) or len(records) > _MAX_ITEMS or any(not isinstance(item, dict) for item in records):
            raise MetadataError(f"metadata {key} must be a bounded array")
        allowed = _RESOURCE_FIELDS[key]
        for record in records:
            if set(record) - allowed:
                raise MetadataError(f"metadata {key} contains an unsupported field")
            if len(record) > len(allowed) or any(
                not isinstance(value, (str, int, float, bool)) and value is not None
                for value in record.values()
            ):
                raise MetadataError(f"metadata {key} records must contain scalar fields")
    collection = payload.get("collection")
    if collection is not None:
        if not isinstance(collection, dict) or set(collection) - set(_RESOURCES):
            raise MetadataError("metadata collection contains an unsupported resource")
        for status in collection.values():
            if not isinstance(status, dict) or not isinstance(status.get("available"), bool):
                raise MetadataError("metadata collection status is malformed")
            allowed_status = {"available", "pages", "truncated", "reason", "retry_after_seconds", "rate_limit_reset_epoch"}
            if set(status) - allowed_status:
                raise MetadataError("metadata collection status contains an unsupported field")
            pages = status.get("pages")
            if isinstance(pages, bool) or not isinstance(pages, int) or not 0 <= pages <= 50:
                raise MetadataError("metadata collection pages are out of bounds")
            if not isinstance(status.get("truncated"), bool):
                raise MetadataError("metadata collection truncated must be boolean")
            reason = status.get("reason")
            if reason is not None and (not isinstance(reason, str) or not reason or len(reason) > 64):
                raise MetadataError("metadata collection reason is malformed")
            retry_after = status.get("retry_after_seconds")
            if retry_after is not None and (isinstance(retry_after, bool) or not isinstance(retry_after, int) or not 0 <= retry_after <= 86400):
                raise MetadataError("metadata retry_after_seconds is out of bounds")
            reset_epoch = status.get("rate_limit_reset_epoch")
            if reset_epoch is not None and (isinstance(reset_epoch, bool) or not isinstance(reset_epoch, int) or not 0 <= reset_epoch <= 4102444800):
                raise MetadataError("metadata rate_limit_reset_epoch is out of bounds")
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
    if isinstance(collection, dict) and collection:
        summary["collection"] = {
            key: {field: status[field] for field in ("available", "pages", "truncated", "reason", "retry_after_seconds", "rate_limit_reset_epoch") if field in status}
            for key, status in sorted(collection.items())
            if isinstance(status, dict)
        }
    return summary

__all__ = ["MAX_METADATA_BYTES", "MAX_METADATA_NESTING", "MetadataError", "SCHEMA_VERSION", "load_metadata", "summarize_metadata", "validate_metadata"]
