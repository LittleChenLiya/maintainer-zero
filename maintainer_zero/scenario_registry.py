"""Validation for versioned, declarative continuity scenario registries.

Registry documents are data-only metadata. Loading one never imports an
entrypoint, evaluates a formula, or executes repository-controlled code.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping

REGISTRY_SCHEMA_VERSION = 1
SCENARIO_SCHEMA_VERSION = 1
MAX_REGISTRY_BYTES = 1_048_576
MAX_SCENARIOS = 100
_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_SOURCES = {"observed", "assumed", "configuration", "unknown"}
_MODES = {"builtin", "declarative"}
_SEVERITIES = {"info", "low", "medium", "high"}
_TYPES = {"boolean", "integer", "number", "string"}
_FORBIDDEN_KEYS = {"command", "exec", "module", "script", "shell"}
_MAX_ITEMS = 100


class ScenarioRegistryError(ValueError):
    """Raised when a registry document is malformed or outside its safety envelope."""


class ScenarioSpecError(ScenarioRegistryError):
    """Backward-compatible name for validating one standalone scenario."""


def _obj(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ScenarioRegistryError(f"{label} must be a JSON object")
    return value


def _text(value: Any, label: str, limit: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScenarioRegistryError(f"{label} must be a non-empty string")
    if len(value) > limit:
        raise ScenarioRegistryError(f"{label} is too long")
    return value


def _texts(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ScenarioRegistryError(f"{label} must be a non-empty list")
    return [_text(item, f"{label}[{index}]", 2000) for index, item in enumerate(value)]


def _semver(value: Any, label: str) -> str:
    value = _text(value, label, 32)
    if not _SEMVER_RE.fullmatch(value):
        raise ScenarioRegistryError(f"{label} must use MAJOR.MINOR.PATCH format")
    return value


def _validate_registry_scenario(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one scenario and return a detached copy."""
    scenario = _obj(payload, "scenario")
    if scenario.get("schema_version") != SCENARIO_SCHEMA_VERSION:
        raise ScenarioRegistryError(
            f"unsupported scenario schema_version: {scenario.get('schema_version')!r}"
        )
    scenario_id = _text(scenario.get("id"), "scenario.id", 64)
    if not _ID_RE.fullmatch(scenario_id):
        raise ScenarioRegistryError("scenario.id must contain lowercase letters, digits, and hyphens")
    _semver(scenario.get("version"), "scenario.version")
    for field in ("title", "summary"):
        _text(scenario.get(field), f"scenario.{field}")

    trigger = _obj(scenario.get("trigger"), "scenario.trigger")
    _text(trigger.get("type"), "scenario.trigger.type", 128)
    _text(trigger.get("description"), "scenario.trigger.description")
    if "duration_days" in trigger:
        days = trigger["duration_days"]
        if isinstance(days, bool) or not isinstance(days, int) or days < 0:
            raise ScenarioRegistryError("scenario.trigger.duration_days must be a non-negative integer")

    _texts(scenario.get("assumptions"), "scenario.assumptions")
    inputs = scenario.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise ScenarioRegistryError("scenario.inputs must be a non-empty list")
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
    return copy.deepcopy(scenario)


def _reject_forbidden(value: Any, path: str = "scenario") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                raise ScenarioSpecError(f"executable field is not allowed: {path}.{key}")
            _reject_forbidden(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden(child, f"{path}[{index}]")


def _validate_legacy_scenario(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the original standalone scenario document format."""
    scenario = _obj(payload, "scenario document")
    _reject_forbidden(scenario)
    if scenario.get("schema_version") != SCENARIO_SCHEMA_VERSION:
        raise ScenarioSpecError(f"unsupported scenario schema_version: {scenario.get('schema_version')!r}")
    scenario_id = scenario.get("id")
    if not isinstance(scenario_id, str) or not _ID_RE.fullmatch(scenario_id):
        raise ScenarioSpecError("scenario id must be lowercase kebab-case")
    _text(scenario.get("version"), "scenario version")
    _text(scenario.get("title"), "scenario title")
    _text(scenario.get("description"), "scenario description")
    assumptions = scenario.get("assumptions")
    if not isinstance(assumptions, list) or not assumptions or len(assumptions) > _MAX_ITEMS:
        raise ScenarioSpecError("scenario assumptions must be a non-empty bounded array")
    for item in assumptions:
        _text(item, "scenario assumption")
    inputs = scenario.get("inputs", [])
    if not isinstance(inputs, list) or len(inputs) > _MAX_ITEMS:
        raise ScenarioSpecError("scenario inputs must be a bounded array")
    names: set[str] = set()
    for item in inputs:
        if not isinstance(item, dict):
            raise ScenarioSpecError("scenario input must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not _ID_RE.fullmatch(name) or name in names:
            raise ScenarioSpecError("scenario input names must be unique kebab-case")
        names.add(name)
        if item.get("type") not in _TYPES:
            raise ScenarioSpecError(f"unsupported input type for {name!r}")
        if not isinstance(item.get("required", True), bool):
            raise ScenarioSpecError(f"scenario input required flag must be boolean: {name!r}")
    events = scenario.get("events")
    if not isinstance(events, list) or not events or len(events) > _MAX_ITEMS:
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
    if not isinstance(findings, list) or not findings or len(findings) > _MAX_ITEMS:
        raise ScenarioSpecError("scenario findings must be a non-empty bounded array")
    finding_ids: set[str] = set()
    for finding in findings:
        if not isinstance(finding, dict):
            raise ScenarioSpecError("scenario finding must be an object")
        finding_id = finding.get("id")
        if not isinstance(finding_id, str) or not _ID_RE.fullmatch(finding_id) or finding_id in finding_ids:
            raise ScenarioSpecError("scenario finding ids must be unique kebab-case")
        finding_ids.add(finding_id)
        if finding.get("severity") not in _SEVERITIES:
            raise ScenarioSpecError(f"unsupported finding severity: {finding_id!r}")
        _text(finding.get("title"), "finding title")
        _text(finding.get("action"), "finding action")
    score = scenario.get("score")
    if not isinstance(score, dict) or not isinstance(score.get("formula"), str) or not score["formula"].strip():
        raise ScenarioSpecError("scenario score must include a formula description")
    if score.get("range", [0, 100]) != [0, 100]:
        raise ScenarioSpecError("scenario score range must be [0, 100]")
    return copy.deepcopy(scenario)


def validate_scenario(payload: Any) -> dict[str, Any]:
    """Validate either a standalone legacy scenario or a registry scenario."""
    if not isinstance(payload, Mapping):
        raise ScenarioSpecError("scenario document must be a JSON object")
    # Registry entries carry a trigger and evidence-bound input sources. The
    # legacy format remains supported for existing examples and CLI users.
    if "trigger" in payload or "summary" in payload or "execution" in payload:
        _reject_forbidden(payload)
        try:
            return _validate_registry_scenario(payload)
        except ScenarioRegistryError as exc:
            raise ScenarioSpecError(str(exc)) from exc
    return _validate_legacy_scenario(payload)


def load_scenario(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    try:
        if path.stat().st_size > MAX_REGISTRY_BYTES:
            raise ScenarioSpecError(f"scenario document exceeds {MAX_REGISTRY_BYTES} bytes")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ScenarioSpecError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScenarioSpecError(f"Invalid scenario document: {path}") from exc
    return validate_scenario(payload)


def validate_registry(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a registry and return a detached copy with stable scenarios."""
    registry = _obj(payload, "registry")
    if registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ScenarioRegistryError(
            f"unsupported registry schema_version: {registry.get('schema_version')!r}"
        )
    _text(registry.get("id"), "registry.id", 64)
    _semver(registry.get("version"), "registry.version")
    scenarios = registry.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ScenarioRegistryError("registry.scenarios must be a non-empty list")
    if len(scenarios) > MAX_SCENARIOS:
        raise ScenarioRegistryError(f"registry.scenarios exceeds limit of {MAX_SCENARIOS}")
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
    """Load bounded UTF-8 JSON and validate it without executing its contents."""
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


__all__ = [
    "MAX_REGISTRY_BYTES", "REGISTRY_SCHEMA_VERSION", "SCENARIO_SCHEMA_VERSION",
    "ScenarioRegistryError", "bundled_registry_path", "load_bundled_registry",
    "load_registry", "scenario_ids", "validate_registry", "validate_scenario",
]
