"""Validate declarative, non-executable continuity scenario documents."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

SCENARIO_SCHEMA_VERSION = 1
_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SEVERITIES = {"info", "low", "medium", "high"}
_TYPES = {"boolean", "integer", "number", "string"}
_FORBIDDEN_KEYS = {"command", "entrypoint", "exec", "module", "script", "shell"}
_MAX_ITEMS = 100
_MAX_TEXT = 4000

class ScenarioSpecError(ValueError):
    """Raised when a declarative scenario does not satisfy the schema."""

def load_scenario(path: str | Path) -> dict[str, Any]:
    scenario_path = Path(path)
    try:
        payload = json.loads(scenario_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScenarioSpecError(f"Invalid scenario document: {scenario_path}") from exc
    return validate_scenario(payload)

def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > _MAX_TEXT:
        raise ScenarioSpecError(f"scenario {field} must be a non-empty bounded string")
    if any(ord(char) < 32 and char not in "\t\n" for char in value):
        raise ScenarioSpecError(f"scenario {field} contains control characters")
    return value

def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list) or not value or len(value) > _MAX_ITEMS:
        raise ScenarioSpecError(f"scenario {field} must be a non-empty bounded array")
    return value

def _reject_forbidden(value: Any, path: str = "scenario") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                raise ScenarioSpecError(f"executable field is not allowed: {path}.{key}")
            _reject_forbidden(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden(child, f"{path}[{index}]")

def validate_scenario(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ScenarioSpecError("scenario document must be a JSON object")
    _reject_forbidden(payload)
    if payload.get("schema_version") != SCENARIO_SCHEMA_VERSION:
        raise ScenarioSpecError(f"unsupported scenario schema_version: {payload.get('schema_version')!r}")
    scenario_id = payload.get("id")
    if not isinstance(scenario_id, str) or not _ID.fullmatch(scenario_id):
        raise ScenarioSpecError("scenario id must be lowercase kebab-case")
    _text(payload.get("version"), "version")
    _text(payload.get("title"), "title")
    _text(payload.get("description"), "description")
    for assumption in _list(payload.get("assumptions"), "assumptions"):
        _text(assumption, "assumption")
    inputs = payload.get("inputs", [])
    if not isinstance(inputs, list) or len(inputs) > _MAX_ITEMS:
        raise ScenarioSpecError("scenario inputs must be a bounded array")
    names: set[str] = set()
    for item in inputs:
        if not isinstance(item, dict):
            raise ScenarioSpecError("scenario input must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not _ID.fullmatch(name) or name in names:
            raise ScenarioSpecError("scenario input names must be unique kebab-case")
        names.add(name)
        if item.get("type") not in _TYPES:
            raise ScenarioSpecError(f"unsupported input type for {name!r}")
        if not isinstance(item.get("required", True), bool):
            raise ScenarioSpecError(f"scenario input required flag must be boolean: {name!r}")
    previous_day = -1
    for event in _list(payload.get("events"), "events"):
        if not isinstance(event, dict):
            raise ScenarioSpecError("scenario event must be an object")
        day = event.get("day")
        if isinstance(day, bool) or not isinstance(day, int) or day < 0 or day < previous_day:
            raise ScenarioSpecError("scenario event days must be non-negative and ordered")
        previous_day = day
        _text(event.get("name"), "event name")
        _text(event.get("impact"), "event impact")
    finding_ids: set[str] = set()
    for finding in _list(payload.get("findings"), "findings"):
        if not isinstance(finding, dict):
            raise ScenarioSpecError("scenario finding must be an object")
        finding_id = finding.get("id")
        if not isinstance(finding_id, str) or not _ID.fullmatch(finding_id) or finding_id in finding_ids:
            raise ScenarioSpecError("scenario finding ids must be unique kebab-case")
        finding_ids.add(finding_id)
        if finding.get("severity") not in _SEVERITIES:
            raise ScenarioSpecError(f"unsupported finding severity: {finding_id!r}")
        _text(finding.get("title"), "finding title")
        _text(finding.get("action"), "finding action")
    score = payload.get("score")
    if not isinstance(score, dict) or not isinstance(score.get("formula"), str) or not score["formula"].strip():
        raise ScenarioSpecError("scenario score must include a formula description")
    if score.get("range", [0, 100]) != [0, 100]:
        raise ScenarioSpecError("scenario score range must be [0, 100]")
    return payload

__all__ = ["SCENARIO_SCHEMA_VERSION", "ScenarioSpecError", "load_scenario", "validate_scenario"]
