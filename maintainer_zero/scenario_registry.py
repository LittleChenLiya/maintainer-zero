"""Validate bounded, declarative continuity scenario documents and registries."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping

REGISTRY_SCHEMA_VERSION = 1
SCENARIO_SCHEMA_VERSION = 1
MAX_REGISTRY_BYTES = 1_048_576
MAX_SCENARIO_BYTES = 1_048_576
MAX_SCENARIOS = 100
_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_LEGACY_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_SEVERITIES = {"info", "low", "medium", "high"}
_INPUT_TYPES = {"boolean", "integer", "number", "string"}
_SOURCES = {"observed", "assumed", "configuration", "unknown"}
_MODES = {"builtin", "declarative"}


class ScenarioSpecError(ValueError):
    """Raised when a standalone scenario is malformed or unsafe."""


class ScenarioRegistryError(ScenarioSpecError):
    """Raised when a versioned registry is malformed or unsafe."""


def _obj(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ScenarioRegistryError(f"{label} must be a JSON object")
    return value


def _text(value: Any, label: str, limit: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScenarioRegistryError(f"{label} must be a non-empty string")
    if len(value) > limit:
        raise ScenarioRegistryError(f"{label} is too long")
    if any(ord(char) < 32 and char not in "\t\n" for char in value):
        raise ScenarioRegistryError(f"{label} contains control characters")
    return value


def _texts(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > 100:
        raise ScenarioRegistryError(f"{label} must be a non-empty bounded list")
    return [_text(item, f"{label}[{index}]", 2000) for index, item in enumerate(value)]


def _semver(value: Any, label: str) -> str:
    value = _text(value, label, 32)
    if not _SEMVER_RE.fullmatch(value):
        raise ScenarioRegistryError(f"{label} must use MAJOR.MINOR.PATCH format")
    return value


def _reject_forbidden(value: Any, path: str = "scenario", *, allow_entrypoint: bool = False) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in {"command", "exec", "module", "script", "shell"} or (lowered == "entrypoint" and not allow_entrypoint):
                raise ScenarioSpecError(f"executable field is not allowed: {path}.{key}")
            _reject_forbidden(child, f"{path}.{key}", allow_entrypoint=allow_entrypoint)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden(child, f"{path}[{index}]", allow_entrypoint=allow_entrypoint)


def _validate_legacy_scenario(payload: Mapping[str, Any]) -> dict[str, Any]:
    scenario = _obj(payload, "scenario document")
    _reject_forbidden(scenario)
    if scenario.get("schema_version") != SCENARIO_SCHEMA_VERSION:
        raise ScenarioSpecError(f"unsupported scenario schema_version: {scenario.get('schema_version')!r}")
    scenario_id = scenario.get("id")
    if not isinstance(scenario_id, str) or not _LEGACY_ID_RE.fullmatch(scenario_id):
        raise ScenarioSpecError("scenario id must be lowercase kebab-case")
    _text(scenario.get("version"), "scenario version")
    _text(scenario.get("title"), "scenario title")
    _text(scenario.get("description"), "scenario description")
    _texts(scenario.get("assumptions"), "scenario assumptions")
    inputs = scenario.get("inputs", [])
    if not isinstance(inputs, list) or len(inputs) > 100:
        raise ScenarioSpecError("scenario inputs must be a bounded array")
    names: set[str] = set()
    for item in inputs:
        if not isinstance(item, dict):
            raise ScenarioSpecError("scenario input must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not _LEGACY_ID_RE.fullmatch(name) or name in names:
            raise ScenarioSpecError("scenario input names must be unique kebab-case")
        names.add(name)
        if item.get("type") not in _INPUT_TYPES:
            raise ScenarioSpecError(f"unsupported input type for {name!r}")
        if not isinstance(item.get("required", True), bool):
            raise ScenarioSpecError(f"scenario input required flag must be boolean: {name!r}")
    events = scenario.get("events")
    if not isinstance(events, list) or not events or len(events) > 100:
        raise ScenarioSpecError("scenario events must be a non-empty bounded array")
    previous_day = -1
    for event in events:
        if not isinstance(event, dict):
            raise ScenarioSpecError("scenario event must be an object")
        day = event.get("day")
        if isinstance(day, bool) or not isinstance(day, int) or day < 0 or day < previous_day:
            raise ScenarioSpecError("scenario event days must be non-negative and ordered")
        previous_day = day
        _text(event.get("name"), "event name")
        _text(event.get("impact"), "event impact")
    findings = scenario.get("findings")
    if not isinstance(findings, list) or not findings or len(findings) > 100:
        raise ScenarioSpecError("scenario findings must be a non-empty bounded list")
    finding_ids: set[str] = set()
    for finding in findings:
        if not isinstance(finding, dict):
            raise ScenarioSpecError("scenario finding must be an object")
        finding_id = finding.get("id")
        if not isinstance(finding_id, str) or not _LEGACY_ID_RE.fullmatch(finding_id) or finding_id in finding_ids:
            raise ScenarioSpecError("scenario finding ids must be unique kebab-case")
        finding_ids.add(finding_id)
        if finding.get("severity") not in _SEVERITIES:
            raise ScenarioSpecError(f"unsupported finding severity: {finding_id!r}")
        _text(finding.get("title"), "finding title")
        _text(finding.get("action"), "finding action")
    score = _obj(scenario.get("score"), "scenario score")
    _text(score.get("formula"), "scenario score formula")
    if score.get("range", [0, 100]) != [0, 100]:
        raise ScenarioSpecError("scenario score range must be [0, 100]")
    return copy.deepcopy(scenario)


def _validate_registry_scenario(payload: Mapping[str, Any]) -> dict[str, Any]:
    scenario = _obj(payload, "scenario")
    if scenario.get("schema_version") != SCENARIO_SCHEMA_VERSION:
        raise ScenarioRegistryError(f"unsupported scenario schema_version: {scenario.get('schema_version')!r}")
    scenario_id = _text(scenario.get("id"), "scenario.id", 64)
    if not _ID_RE.fullmatch(scenario_id):
        raise ScenarioRegistryError("scenario.id must contain lowercase letters, digits, and hyphens")
    _semver(scenario.get("version"), "scenario.version")
    _text(scenario.get("title"), "scenario.title")
    _text(scenario.get("summary"), "scenario.summary")
    trigger = _obj(scenario.get("trigger"), "scenario.trigger")
    _text(trigger.get("type"), "scenario.trigger.type", 128)
    _text(trigger.get("description"), "scenario.trigger.description")
    if "duration_days" in trigger and (isinstance(trigger["duration_days"], bool) or not isinstance(trigger["duration_days"], int) or trigger["duration_days"] < 0):
        raise ScenarioRegistryError("scenario.trigger.duration_days must be a non-negative integer")
    _texts(scenario.get("assumptions"), "scenario.assumptions")
    inputs = scenario.get("inputs")
    if not isinstance(inputs, list) or not inputs or len(inputs) > 100:
        raise ScenarioRegistryError("scenario.inputs must be a non-empty bounded list")
    names: set[str] = set()
    for index, raw in enumerate(inputs):
        item = _obj(raw, f"scenario.inputs[{index}]")
        name = _text(item.get("name"), f"scenario.inputs[{index}].name", 128)
        if name in names:
            raise ScenarioRegistryError(f"duplicate scenario input: {name}")
        names.add(name)
        _text(item.get("description"), f"scenario.inputs[{index}].description")
        source = _text(item.get("source"), f"scenario.inputs[{index}].source", 32)
        if source not in _SOURCES:
            raise ScenarioRegistryError(f"unsupported scenario input source: {source}")
    score = _obj(scenario.get("score"), "scenario.score")
    _text(score.get("formula"), "scenario.score.formula")
    if score.get("range") != [0, 100]:
        raise ScenarioRegistryError("scenario.score.range must be [0, 100]")
    _texts(scenario.get("recovery_actions"), "scenario.recovery_actions")
    _texts(scenario.get("limitations"), "scenario.limitations")
    execution = _obj(scenario.get("execution"), "scenario.execution")
    mode = _text(execution.get("mode"), "scenario.execution.mode", 32)
    if mode not in _MODES:
        raise ScenarioRegistryError(f"unsupported scenario execution mode: {mode}")
    if mode == "builtin":
        entrypoint = _text(execution.get("entrypoint"), "scenario.execution.entrypoint", 200)
        if any(char in entrypoint for char in (";", "|", "&", "\n", "\r")):
            raise ScenarioRegistryError("scenario.execution.entrypoint contains unsafe characters")
    _reject_forbidden(scenario, allow_entrypoint=True)
    return copy.deepcopy(scenario)


def validate_scenario(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate either the legacy standalone or registry scenario format."""
    scenario = _obj(payload, "scenario")
    if "description" in scenario and "summary" not in scenario:
        return _validate_legacy_scenario(scenario)
    return _validate_registry_scenario(scenario)


def load_scenario(path: str | Path, *, max_bytes: int = MAX_SCENARIO_BYTES) -> dict[str, Any]:
    scenario_path = Path(path)
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    try:
        if scenario_path.stat().st_size > max_bytes:
            raise ScenarioSpecError(f"scenario exceeds {max_bytes} bytes")
        payload = json.loads(scenario_path.read_text(encoding="utf-8"))
    except ScenarioSpecError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScenarioSpecError(f"Invalid scenario document: {scenario_path}") from exc
    return validate_scenario(payload)


def validate_registry(payload: Mapping[str, Any]) -> dict[str, Any]:
    registry = _obj(payload, "registry")
    if registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ScenarioRegistryError(f"unsupported registry schema_version: {registry.get('schema_version')!r}")
    _text(registry.get("id"), "registry.id", 64)
    _semver(registry.get("version"), "registry.version")
    scenarios = registry.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios or len(scenarios) > MAX_SCENARIOS:
        raise ScenarioRegistryError(f"registry.scenarios must be a non-empty list of at most {MAX_SCENARIOS}")
    result = copy.deepcopy(registry)
    result["scenarios"] = []
    seen: set[str] = set()
    for item in scenarios:
        scenario = _validate_registry_scenario(item)
        if scenario["id"] in seen:
            raise ScenarioRegistryError(f"duplicate scenario id: {scenario['id']}")
        seen.add(scenario["id"])
        result["scenarios"].append(scenario)
    return result


def load_registry(path: str | Path, *, max_bytes: int = MAX_REGISTRY_BYTES) -> dict[str, Any]:
    path = Path(path)
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    try:
        if path.stat().st_size > max_bytes:
            raise ScenarioRegistryError(f"scenario registry exceeds {max_bytes} bytes")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ScenarioRegistryError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScenarioRegistryError(f"invalid scenario registry: {path}") from exc
    return validate_registry(payload)


def bundled_registry_path() -> Path:
    return Path(__file__).with_name("scenario_registry.json")


def load_bundled_registry() -> dict[str, Any]:
    return load_registry(bundled_registry_path())


def scenario_ids(registry: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(item["id"] for item in validate_registry(registry)["scenarios"]))


def scenario_summary(scenario: Mapping[str, Any]) -> dict[str, Any]:
    """Return a stable, non-executable review summary for one scenario."""
    validated = validate_scenario(scenario)
    trigger = validated.get("trigger", {})
    execution = validated.get("execution", {})
    inputs = validated.get("inputs", [])
    if trigger:
        trigger_summary = {
            "type": trigger.get("type"),
            "duration_days": trigger.get("duration_days"),
        }
    else:
        events = validated.get("events", [])
        trigger_summary = {
            "type": "legacy-event-sequence",
            "duration_days": max((event.get("day", 0) for event in events), default=None),
        }
    actions = list(validated.get("recovery_actions", []))
    if not actions:
        actions = [finding["action"] for finding in validated.get("findings", []) if isinstance(finding, Mapping) and isinstance(finding.get("action"), str)]
    return {
        "schema_version": validated["schema_version"],
        "id": validated["id"],
        "version": validated["version"],
        "title": validated["title"],
        "summary": validated.get("summary", validated.get("description", "")),
        "trigger": trigger_summary,
        "input_sources": {
            item["name"]: item.get("source", "unknown")
            for item in sorted(inputs, key=lambda item: item["name"])
        },
        "recovery_actions": actions,
        "limitations": list(validated.get("limitations", [])),
        "execution_mode": execution.get("mode", "declarative"),
    }


__all__ = [
    "MAX_REGISTRY_BYTES", "MAX_SCENARIO_BYTES", "REGISTRY_SCHEMA_VERSION", "SCENARIO_SCHEMA_VERSION",
    "ScenarioRegistryError", "ScenarioSpecError", "bundled_registry_path",
    "load_bundled_registry", "load_registry", "load_scenario", "scenario_ids",
    "scenario_summary", "validate_registry", "validate_scenario",
]
