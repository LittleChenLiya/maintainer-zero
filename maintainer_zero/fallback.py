"""Bounded, data-only dependency fallback and cold-build evidence plans."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

SCHEMA_VERSION = 1
MAX_PLAN_BYTES = 1_048_576
MAX_ENTRIES = 128
MAX_TEXT = 256
_STATUSES = {"unknown", "planned", "passed", "failed"}
_SOURCES = {"unknown", "mirror", "vendor", "alternate-index", "local"}


class FallbackPlanError(ValueError):
    """Raised when a fallback plan is not a bounded data-only document."""


def _link_like(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT:
        raise FallbackPlanError(f"{field} must be a bounded non-empty string")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise FallbackPlanError(f"{field} contains control characters")
    return value


def load_fallback_plan(path: str | Path) -> dict[str, object]:
    """Load a strict local plan; never executes commands or contacts indexes."""
    target = Path(path)
    try:
        info = target.lstat()
    except OSError as exc:
        raise FallbackPlanError(f"cannot inspect fallback plan: {target}") from exc
    if _link_like(info) or not stat.S_ISREG(info.st_mode):
        raise FallbackPlanError("fallback plan must be a regular file")
    if info.st_size > MAX_PLAN_BYTES:
        raise FallbackPlanError(f"fallback plan exceeds {MAX_PLAN_BYTES} bytes")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FallbackPlanError("invalid fallback plan JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "dependencies"}:
        raise FallbackPlanError("fallback plan fields are invalid")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise FallbackPlanError("unsupported fallback plan schema version")
    entries = payload["dependencies"]
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise FallbackPlanError("fallback dependencies must be a bounded list")
    seen: set[str] = set()
    normalized: list[dict[str, object]] = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"name", "replacement", "source", "cold_build"}:
            raise FallbackPlanError("fallback dependency entry fields are invalid")
        name = _text(entry["name"], "dependency name")
        replacement = _text(entry["replacement"], "replacement")
        source = _text(entry["source"], "source")
        if source not in _SOURCES:
            raise FallbackPlanError(f"unsupported fallback source: {source}")
        key = name.casefold()
        if key in seen:
            raise FallbackPlanError("fallback plan contains duplicate dependencies")
        seen.add(key)
        cold = entry["cold_build"]
        if not isinstance(cold, dict) or set(cold) != {"status", "recorded_at"}:
            raise FallbackPlanError("cold_build evidence fields are invalid")
        status = _text(cold["status"], "cold_build.status")
        if status not in _STATUSES:
            raise FallbackPlanError(f"unsupported cold_build status: {status}")
        recorded_at = _text(cold["recorded_at"], "cold_build.recorded_at")
        normalized.append(
            {
                "name": name,
                "replacement": replacement,
                "source": source,
                "cold_build": {"status": status, "recorded_at": recorded_at},
            }
        )
    normalized.sort(key=lambda item: str(item["name"]).casefold())
    return {"schema_version": SCHEMA_VERSION, "dependencies": normalized}


def summarize_fallback_plan(plan: dict[str, object]) -> dict[str, object]:
    """Return report-safe aggregates while retaining auditable declarations."""
    entries = plan["dependencies"]
    statuses = {status: 0 for status in sorted(_STATUSES)}
    for entry in entries:
        statuses[entry["cold_build"]["status"]] += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "dependency_count": len(entries),
        "cold_build_status_counts": statuses,
        "entries": entries,
        "evidence_kind": "declared-plan",
        "execution": "not-run",
    }
