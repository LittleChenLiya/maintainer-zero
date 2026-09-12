"""Bounded local cache for validated read-only GitHub metadata snapshots."""
from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .github_metadata import MAX_METADATA_BYTES, MetadataError, validate_metadata

CACHE_SCHEMA_VERSION = 1
MAX_CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
_CACHE_KEYS = frozenset(("schema_version", "source", "fetched_at", "expires_at", "ttl_seconds"))
_SOURCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class MetadataCacheError(ValueError):
    """Raised when a local metadata cache is missing, invalid, or stale."""


@dataclass(frozen=True)
class CacheStatus:
    state: str
    source: str | None = None
    fetched_at: str | None = None
    expires_at: str | None = None
    reason: str | None = None

    def as_dict(self) -> dict[str, str]:
        result = {"state": self.state}
        for key in ("source", "fetched_at", "expires_at", "reason"):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        return result


def _normalise_time(value: datetime, *, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise MetadataCacheError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise MetadataCacheError(f"cache {label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MetadataCacheError(f"cache {label} must be an ISO-8601 timestamp") from exc
    return _normalise_time(parsed, label=f"cache {label}")


def _validate_cache_block(cache: Any) -> dict[str, Any]:
    if not isinstance(cache, dict) or set(cache) != _CACHE_KEYS:
        raise MetadataCacheError("metadata cache envelope is malformed")
    if cache.get("schema_version") != CACHE_SCHEMA_VERSION:
        raise MetadataCacheError("unsupported metadata cache schema_version")
    source = cache.get("source")
    if not isinstance(source, str) or not _SOURCE_RE.fullmatch(source):
        raise MetadataCacheError("cache source is malformed")
    ttl = cache.get("ttl_seconds")
    if isinstance(ttl, bool) or not isinstance(ttl, int) or not 1 <= ttl <= MAX_CACHE_TTL_SECONDS:
        raise MetadataCacheError("cache ttl_seconds is out of bounds")
    fetched = _parse_timestamp(cache.get("fetched_at"), label="fetched_at")
    expires = _parse_timestamp(cache.get("expires_at"), label="expires_at")
    if expires != fetched + timedelta(seconds=ttl):
        raise MetadataCacheError("cache expires_at does not match fetched_at and ttl_seconds")
    return {"schema_version": CACHE_SCHEMA_VERSION, "source": source,
            "fetched_at": _timestamp(fetched), "expires_at": _timestamp(expires),
            "ttl_seconds": ttl}


def _open_cache(path: Path):
    """Open a cache without following a symlink or accepting special files."""
    try:
        path_stat = path.lstat()
        if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
            raise MetadataCacheError("metadata cache must be a regular file")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            os.close(descriptor)
            raise MetadataCacheError("metadata cache must be a regular file")
        return os.fdopen(descriptor, "rb")
    except MetadataCacheError:
        raise
    except OSError as exc:
        raise MetadataCacheError(f"invalid metadata cache: {path}") from exc


def _read(path: Path) -> dict[str, Any]:
    try:
        with _open_cache(path) as handle:
            raw = handle.read(MAX_METADATA_BYTES + 1)
        if len(raw) > MAX_METADATA_BYTES:
            raise MetadataCacheError(f"metadata cache exceeds {MAX_METADATA_BYTES} bytes")
        payload = json.loads(raw)
    except MetadataCacheError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise MetadataCacheError(f"invalid metadata cache: {path}") from exc
    if not isinstance(payload, dict):
        raise MetadataCacheError("metadata cache must be a JSON object")
    try:
        validate_metadata(payload)
    except MetadataError as exc:
        raise MetadataCacheError("metadata cache payload is invalid") from exc
    payload["cache"] = _validate_cache_block(payload.get("cache"))
    return payload


def save_metadata_cache(path: str | Path, payload: Mapping[str, Any], *,
                        source: str = "github-api", ttl_seconds: int = 24 * 60 * 60,
                        fetched_at: datetime | None = None) -> dict[str, Any]:
    """Validate and atomically save a bounded metadata cache envelope."""
    if not isinstance(payload, Mapping):
        raise MetadataCacheError("metadata payload must be an object")
    try:
        validate_metadata(dict(payload))
    except MetadataError as exc:
        raise MetadataCacheError("metadata payload is invalid") from exc
    now = _normalise_time(fetched_at or datetime.now(timezone.utc), label="fetched_at")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= MAX_CACHE_TTL_SECONDS:
        raise MetadataCacheError("cache ttl_seconds is out of bounds")
    cache = _validate_cache_block({"schema_version": CACHE_SCHEMA_VERSION, "source": source,
        "fetched_at": _timestamp(now), "expires_at": _timestamp(now + timedelta(seconds=ttl_seconds)),
        "ttl_seconds": ttl_seconds})
    result = dict(payload)
    result["cache"] = cache
    encoded = (json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > MAX_METADATA_BYTES:
        raise MetadataCacheError(f"metadata cache exceeds {MAX_METADATA_BYTES} bytes")
    target = Path(path)
    if target.exists():
        try:
            target_stat = target.lstat()
        except OSError as exc:
            raise MetadataCacheError(f"could not inspect metadata cache: {target}") from exc
        if stat.S_ISLNK(target_stat.st_mode) or not stat.S_ISREG(target_stat.st_mode):
            raise MetadataCacheError("metadata cache target must be a regular file")
    temporary: Path | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
    except OSError as exc:
        raise MetadataCacheError(f"could not write metadata cache: {target}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return result


def cache_status(path: str | Path, *, now: datetime | None = None) -> CacheStatus:
    """Inspect a cache without treating stale data as current."""
    target = Path(path)
    try:
        target.lstat()
    except FileNotFoundError:
        return CacheStatus("missing", reason="not_found")
    except OSError:
        return CacheStatus("invalid", reason="not_found")
    try:
        payload = _read(target)
    except MetadataCacheError as exc:
        return CacheStatus("invalid", reason=str(exc))
    cache = payload["cache"]
    current = _normalise_time(now or datetime.now(timezone.utc), label="now")
    state = "fresh" if current < _parse_timestamp(cache["expires_at"], label="expires_at") else "stale"
    return CacheStatus(state, cache["source"], cache["fetched_at"], cache["expires_at"],
                       None if state == "fresh" else "expired")


def load_metadata_cache(path: str | Path, *, now: datetime | None = None,
                        allow_stale: bool = False) -> dict[str, Any]:
    """Load a validated cache; stale data requires explicit opt-in."""
    target = Path(path)
    payload = _read(target)
    status = cache_status(target, now=now)
    if status.state == "stale" and not allow_stale:
        raise MetadataCacheError("metadata cache is stale; pass allow_stale=True to inspect it")
    return payload


__all__ = ["CACHE_SCHEMA_VERSION", "CacheStatus", "MAX_CACHE_TTL_SECONDS",
           "MetadataCacheError", "cache_status", "load_metadata_cache", "save_metadata_cache"]
