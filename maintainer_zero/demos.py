"""Run bounded, data-only before/after continuity demonstrations."""

from __future__ import annotations

import json
import importlib.resources
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping

from .models import RepoSnapshot
from .scenarios import SCENARIOS

MAX_DEMOS = 10
MAX_DEMO_BYTES = 1_048_576
MAX_SNAPSHOT_ENTRIES = 1000
MAX_COUNT = 1_000_000_000
_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SNAPSHOT_FIELDS = {
    "path", "name", "commits", "contributors", "dependencies",
    "workflows", "codeowners", "release_files",
}


class DemoError(ValueError):
    """Raised when a demo suite is malformed or outside its safety envelope."""


def _is_link_like(info: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & reparse_flag)


def _read_external_suite(path: str | Path) -> bytes:
    target = Path(path)
    if not target.is_absolute():
        target = Path.cwd() / target
    current = Path(target.anchor) if target.anchor else Path()
    parts = target.parts[1:] if target.anchor else target.parts
    for part in parts[:-1]:
        current /= part
        try:
            info = current.lstat()
        except OSError as exc:
            raise DemoError(f"cannot inspect demo suite parent: {current}") from exc
        if _is_link_like(info) or not stat.S_ISDIR(info.st_mode):
            raise DemoError("demo suite parent must be a real directory")
    target = Path(os.path.normpath(os.fspath(target)))
    try:
        initial = target.lstat()
    except OSError as exc:
        raise DemoError(f"cannot inspect demo suite: {target}") from exc
    if _is_link_like(initial) or not stat.S_ISREG(initial.st_mode):
        raise DemoError("demo suite must be a regular file")
    if initial.st_size > MAX_DEMO_BYTES:
        raise DemoError(f"demo suite exceeds {MAX_DEMO_BYTES} bytes")
    descriptor: int | None = None
    try:
        descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        if _is_link_like(opened) or not stat.S_ISREG(opened.st_mode):
            raise DemoError("demo suite descriptor is not a regular file")
        identity = (getattr(initial, "st_dev", 0), getattr(initial, "st_ino", 0))
        if (getattr(opened, "st_dev", 0), getattr(opened, "st_ino", 0)) != identity:
            raise DemoError("demo suite changed before reading")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            raw = handle.read(MAX_DEMO_BYTES + 1)
        if len(raw) > MAX_DEMO_BYTES:
            raise DemoError(f"demo suite exceeds {MAX_DEMO_BYTES} bytes")
        after = target.lstat()
        if (
            _is_link_like(after)
            or not stat.S_ISREG(after.st_mode)
            or (getattr(after, "st_dev", 0), getattr(after, "st_ino", 0)) != identity
            or after.st_size != initial.st_size
            or getattr(after, "st_mtime_ns", None) != getattr(initial, "st_mtime_ns", None)
            or getattr(after, "st_ctime_ns", None) != getattr(initial, "st_ctime_ns", None)
            or after.st_size != len(raw)
        ):
            raise DemoError("demo suite changed during reading")
        return raw
    except DemoError:
        raise
    except OSError as exc:
        raise DemoError(f"cannot read demo suite: {target}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DemoError(f"demo suite contains duplicate object key: {key}")
        result[key] = value
    return result


def _reject_nonstandard_number(value: str) -> None:
    raise DemoError(f"demo suite contains non-standard JSON number: {value}")


def _text(value: Any, label: str, limit: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise DemoError(f"{label} must be a non-empty string of at most {limit} characters")
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        raise DemoError(f"{label} contains control characters")
    return value


def _count(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_COUNT:
        raise DemoError(f"{label} must be an integer from 0 to {MAX_COUNT}")
    return value


def _texts(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_SNAPSHOT_ENTRIES:
        raise DemoError(f"{label} must be a list of at most {MAX_SNAPSHOT_ENTRIES} strings")
    return [_text(item, f"{label}[{index}]") for index, item in enumerate(value)]


def _mapping(value: Any, label: str) -> Mapping:
    if not isinstance(value, Mapping) or len(value) > MAX_SNAPSHOT_ENTRIES:
        raise DemoError(f"{label} must be an object with at most {MAX_SNAPSHOT_ENTRIES} entries")
    return value


def _snapshot(value: Any, label: str) -> RepoSnapshot:
    if isinstance(value, RepoSnapshot):
        # Revalidate normalized suites too; mutable dataclasses are not proof
        # that values have already passed the data-only input boundary.
        value = {field: getattr(value, field) for field in _SNAPSHOT_FIELDS}
    if not isinstance(value, Mapping):
        raise DemoError(f"{label} must be an object")
    if set(value) != _SNAPSHOT_FIELDS:
        raise DemoError(f"{label} must contain exactly the snapshot fields")
    commits = _count(value["commits"], f"{label}.commits")
    contributors = {
        _text(name, f"{label}.contributors key"): _count(count, f"{label}.contributors count")
        for name, count in _mapping(value["contributors"], f"{label}.contributors").items()
    }
    if sum(contributors.values()) > commits:
        raise DemoError(f"{label}.contributors counts cannot exceed commits")
    codeowners = {
        _text(pattern, f"{label}.codeowners key"): _texts(owners, f"{label}.codeowners owners")
        for pattern, owners in _mapping(value["codeowners"], f"{label}.codeowners").items()
    }
    return RepoSnapshot(
        path=_text(value["path"], f"{label}.path"),
        name=_text(value["name"], f"{label}.name"),
        commits=commits,
        contributors=contributors,
        codeowners=codeowners,
        **{field: _texts(value[field], f"{label}.{field}") for field in (
            "dependencies", "workflows", "release_files",
        )},
    )


def validate_demo_suite(payload: Any) -> dict[str, Any]:
    if (not isinstance(payload, Mapping) or type(payload.get("schema_version")) is not int
            or payload.get("schema_version") != 1):
        raise DemoError("demo suite schema_version must be 1")
    if set(payload) != {"schema_version", "demos"}:
        raise DemoError("demo suite must contain exactly schema_version and demos")
    demos = payload.get("demos")
    if not isinstance(demos, list) or not 1 <= len(demos) <= MAX_DEMOS:
        raise DemoError(f"demo suite must contain 1..{MAX_DEMOS} demos")
    seen: set[str] = set()
    result = []
    for index, item in enumerate(demos):
        if not isinstance(item, Mapping):
            raise DemoError(f"demos[{index}] must be an object")
        if set(item) != {"id", "scenario", "before", "after", "lesson"}:
            raise DemoError(f"demos[{index}] must contain exactly the demo fields")
        demo_id = item.get("id")
        scenario = item.get("scenario")
        if (not isinstance(demo_id, str) or len(demo_id) > 64
                or not _ID_RE.fullmatch(demo_id) or demo_id in seen):
            raise DemoError(f"demos[{index}].id must be unique lowercase kebab-case of at most 64 characters")
        if not isinstance(scenario, str) or scenario not in SCENARIOS:
            raise DemoError(f"demos[{index}].scenario is not a built-in scenario")
        before = _snapshot(item.get("before"), f"demos[{index}].before")
        after = _snapshot(item.get("after"), f"demos[{index}].after")
        lesson = _text(item.get("lesson"), f"demos[{index}].lesson", 4000)
        seen.add(demo_id)
        result.append({"id": demo_id, "scenario": scenario, "before": before, "after": after, "lesson": lesson})
    return {"schema_version": 1, "demos": result}


def load_demo_suite(path: str | Path | None = None) -> dict[str, Any]:
    try:
        if path is None:
            raw = importlib.resources.files("maintainer_zero").joinpath("continuity_demos.json").read_bytes()
            source_label = "maintainer_zero/continuity_demos.json"
        else:
            raw = _read_external_suite(path)
            source_label = str(path)
        if len(raw) > MAX_DEMO_BYTES:
            raise DemoError(f"demo suite exceeds {MAX_DEMO_BYTES} bytes")
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_object_keys,
            parse_constant=_reject_nonstandard_number,
        )
    except DemoError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise DemoError(f"invalid demo suite: {source_label if 'source_label' in locals() else path}") from exc
    return validate_demo_suite(payload)


def run_demo_suite(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    suite = validate_demo_suite(payload)
    output = []
    for demo in suite["demos"]:
        function = SCENARIOS[demo["scenario"]]
        before = function(demo["before"], 30)
        after = function(demo["after"], 30)
        output.append({
            "id": demo["id"],
            "scenario": demo["scenario"],
            "before_score": before.score,
            "after_score": after.score,
            "score_delta": after.score - before.score,
            "improved": after.score > before.score,
            "lesson": demo["lesson"],
        })
    return output


__all__ = ["DemoError", "load_demo_suite", "run_demo_suite", "validate_demo_suite"]
