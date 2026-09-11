"""Run bounded, data-only before/after continuity demonstrations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .models import RepoSnapshot
from .scenarios import SCENARIOS

MAX_DEMOS = 10
_SNAPSHOT_FIELDS = {
    "path", "name", "commits", "contributors", "dependencies",
    "workflows", "codeowners", "release_files",
}


class DemoError(ValueError):
    """Raised when a demo suite is malformed or outside its safety envelope."""


def _snapshot(value: Any, label: str) -> RepoSnapshot:
    if isinstance(value, RepoSnapshot):
        return value
    if not isinstance(value, Mapping):
        raise DemoError(f"{label} must be an object")
    if set(value) != _SNAPSHOT_FIELDS:
        raise DemoError(f"{label} must contain exactly the snapshot fields")
    try:
        snapshot = RepoSnapshot(**dict(value))
    except (TypeError, ValueError) as exc:
        raise DemoError(f"{label} is not a valid repository snapshot") from exc
    if snapshot.commits < 0 or not isinstance(snapshot.contributors, dict):
        raise DemoError(f"{label} contains invalid counts")
    return snapshot


def validate_demo_suite(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
        raise DemoError("demo suite schema_version must be 1")
    demos = payload.get("demos")
    if not isinstance(demos, list) or not 1 <= len(demos) <= MAX_DEMOS:
        raise DemoError(f"demo suite must contain 1..{MAX_DEMOS} demos")
    seen: set[str] = set()
    result = []
    for index, item in enumerate(demos):
        if not isinstance(item, Mapping):
            raise DemoError(f"demos[{index}] must be an object")
        demo_id = item.get("id")
        scenario = item.get("scenario")
        if not isinstance(demo_id, str) or not demo_id or demo_id in seen:
            raise DemoError(f"demos[{index}].id must be unique and non-empty")
        if not isinstance(scenario, str) or scenario not in SCENARIOS:
            raise DemoError(f"demos[{index}].scenario is not a built-in scenario")
        before = _snapshot(item.get("before"), f"demos[{index}].before")
        after = _snapshot(item.get("after"), f"demos[{index}].after")
        if not isinstance(item.get("lesson"), str) or not item["lesson"].strip():
            raise DemoError(f"demos[{index}].lesson must be non-empty")
        seen.add(demo_id)
        result.append({"id": demo_id, "scenario": scenario, "before": before, "after": after, "lesson": item["lesson"]})
    return {"schema_version": 1, "demos": result}


def load_demo_suite(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DemoError(f"invalid demo suite: {path}") from exc
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
