"""Build privacy-preserving, non-ranking benchmark summaries from reports."""
from __future__ import annotations

import json
import math
import os
import stat
from typing import Any, Mapping
from pathlib import Path

BENCHMARK_SCHEMA_VERSION = 1
_SEVERITIES = ("high", "medium", "low", "info", "unknown")
_CONFIDENCES = frozenset({"high", "medium", "low", "unknown"})
_KNOWN_SCENARIOS = frozenset({"maintainer-zero", "dependency-yanked", "ci-outage"})
_KNOWN_METADATA = ("repository", "issues", "pull_requests", "reviews", "releases")
_MAX_SCENARIOS = 128
_MAX_TEXT = 128
MAX_BENCHMARK_BYTES = 1_048_576
_MAX_FINDINGS = 500
_SUMMARY_KEYS = frozenset({
    "schema_version", "tool", "rule_version", "scope",
    "not_a_ranking", "privacy", "overall_score", "scenarios",
    "metadata",
})
_TOOL_KEYS = frozenset({"name", "version"})
_PRIVACY_KEYS = frozenset({
    "repository_identity", "contributor_identity", "raw_records",
    "repository_content_upload",
})
_METADATA_KEYS = frozenset({"available_resources", "unknown_resources"})
_SCENARIO_KEYS = frozenset({"id", "score", "confidence", "finding_counts"})


class BenchmarkError(ValueError):
    """Raised when a report cannot be reduced to a safe benchmark summary."""


def _link_like(info: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & reparse_flag)


def _safe_benchmark_file(path: str | Path) -> tuple[Path, os.stat_result]:
    """Open only a regular file whose parent path cannot redirect via a link."""
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
            raise BenchmarkError(f"cannot inspect benchmark parent: {current}") from exc
        if _link_like(info) or not stat.S_ISDIR(info.st_mode):
            raise BenchmarkError("benchmark parent must be a real directory")
    target = Path(os.path.normpath(os.fspath(target)))
    try:
        info = target.lstat()
    except OSError as exc:
        raise BenchmarkError(f"cannot inspect benchmark summary: {target}") from exc
    if _link_like(info) or not stat.S_ISREG(info.st_mode):
        raise BenchmarkError("benchmark summary must be a regular file")
    return target, info


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BenchmarkError(f"benchmark contains duplicate object key: {key}")
        result[key] = value
    return result


def _reject_nonstandard_number(value: str) -> None:
    raise BenchmarkError(f"benchmark contains non-standard JSON number: {value}")


def load_benchmark(path: str | Path) -> dict[str, Any]:
    """Load and validate a shareable benchmark summary without executing code."""
    target, info = _safe_benchmark_file(path)
    if info.st_size > MAX_BENCHMARK_BYTES:
        raise BenchmarkError(f"benchmark summary exceeds {MAX_BENCHMARK_BYTES} bytes")
    try:
        with target.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if _link_like(opened) or not stat.S_ISREG(opened.st_mode):
                raise BenchmarkError("benchmark descriptor is not a regular file")
            if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                raise BenchmarkError("benchmark summary changed before reading")
            raw = handle.read(MAX_BENCHMARK_BYTES + 1)
        if len(raw) > MAX_BENCHMARK_BYTES:
            raise BenchmarkError(f"benchmark summary exceeds {MAX_BENCHMARK_BYTES} bytes")
        after = target.lstat()
        if ((after.st_dev, after.st_ino) != (info.st_dev, info.st_ino)
                or after.st_size != info.st_size
                or getattr(after, "st_mtime_ns", None) != getattr(info, "st_mtime_ns", None)):
            raise BenchmarkError("benchmark summary changed during reading")
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_object_keys,
            parse_constant=_reject_nonstandard_number,
        )
    except BenchmarkError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise BenchmarkError("invalid benchmark summary JSON") from exc
    return validate_benchmark(payload)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > _MAX_TEXT:
        raise BenchmarkError(f"{field} must be a bounded non-empty string")
    # ``isprintable`` also rejects Unicode line/paragraph separators and C1
    # controls, which are not caught by an ASCII-only range check.
    if any(not char.isprintable() for char in value):
        raise BenchmarkError(f"{field} contains control characters")
    return value


def _score(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BenchmarkError(f"{field} must be a finite score")
    # Converting an arbitrarily large JSON integer to float raises
    # OverflowError.  Treat it as invalid input instead of leaking an
    # exception through the CLI.  Decimal scores are still normalized using
    # the same deterministic rounding rule as before.
    try:
        numeric = float(value)
    except (OverflowError, ValueError):
        raise BenchmarkError(f"{field} must be a finite score") from None
    if not math.isfinite(numeric):
        raise BenchmarkError(f"{field} must be a finite score")
    # Validate the source value before rounding; otherwise values such as
    # 100.4 or -0.4 would silently become an in-range integer score.
    if not 0 <= numeric <= 100:
        raise BenchmarkError(f"{field} must be between 0 and 100")
    score = round(numeric)
    return score


def build_benchmark(report: Mapping[str, Any]) -> dict[str, Any]:
    """Project a continuity report without retaining repository identity or raw records."""
    if not isinstance(report, Mapping):
        raise BenchmarkError("continuity report must be an object")
    rule_version = _text(report.get("rule_version"), "rule_version")
    tool = report.get("tool")
    if tool is None:
        tool_summary = None
    elif isinstance(tool, Mapping) and tool.get("name") == "Maintainer-Zero":
        tool_summary = {"name": "Maintainer-Zero", "version": _text(tool.get("version"), "tool.version")}
    else:
        raise BenchmarkError("continuity report tool metadata is invalid")
    results = report.get("results")
    if not isinstance(results, list) or len(results) > _MAX_SCENARIOS:
        raise BenchmarkError("continuity report results must be a bounded array")
    scenarios: list[dict[str, Any]] = []
    scores: list[int] = []
    seen: set[str] = set()
    for index, result in enumerate(results):
        if not isinstance(result, Mapping):
            raise BenchmarkError(f"result {index} must be an object")
        scenario = _text(result.get("scenario"), f"result {index} scenario")
        if scenario not in _KNOWN_SCENARIOS:
            raise BenchmarkError("benchmark scenario is not one of the reviewed core scenarios")
        key = scenario.casefold()
        if key in seen:
            raise BenchmarkError("benchmark contains duplicate scenarios")
        seen.add(key)
        score = _score(result.get("score"), f"result {index} score")
        confidence = result.get("confidence", "unknown")
        if not isinstance(confidence, str) or confidence not in _CONFIDENCES:
            raise BenchmarkError(f"result {index} confidence is invalid")
        findings = result.get("findings", [])
        if not isinstance(findings, list) or len(findings) > 500:
            raise BenchmarkError(f"result {index} findings must be a bounded array")
        counts = {severity: 0 for severity in _SEVERITIES}
        for finding in findings:
            if not isinstance(finding, Mapping):
                raise BenchmarkError("benchmark finding must be an object")
            severity = finding.get("severity", "unknown")
            if not isinstance(severity, str):
                raise BenchmarkError("benchmark finding severity is invalid")
            severity = severity.casefold()
            if severity not in counts:
                raise BenchmarkError("benchmark finding severity is invalid")
            counts[severity] += 1
        scenarios.append({"id": scenario, "score": score, "confidence": confidence, "finding_counts": counts})
        scores.append(score)
    scenarios.sort(key=lambda item: item["id"].casefold())
    metadata = report.get("github_metadata")
    available: list[str] = []
    unknown: list[str] = list(_KNOWN_METADATA)
    if isinstance(metadata, Mapping):
        permissions = metadata.get("permissions")
        if isinstance(permissions, Mapping):
            available = [name for name in _KNOWN_METADATA if permissions.get(name) is True]
            unknown = [name for name in _KNOWN_METADATA if permissions.get(name) is not True]
    return {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "tool": tool_summary,
        "rule_version": rule_version,
        "scope": "privacy-preserving-summary",
        "not_a_ranking": True,
        "privacy": {
            "repository_identity": "omitted",
            "contributor_identity": "omitted",
            "raw_records": "omitted",
            "repository_content_upload": False,
        },
        "overall_score": round(sum(scores) / len(scores)) if scores else None,
        "scenarios": scenarios,
        "metadata": {"available_resources": available, "unknown_resources": unknown},
    }


def _bounded_count(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _MAX_FINDINGS:
        raise BenchmarkError(f"{field} must be an integer from 0 to {_MAX_FINDINGS}")
    return value


def _integer_score(value: object, field: str) -> int:
    """Validate the canonical integer score emitted by the exporter."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise BenchmarkError(f"{field} must be an integer score")
    return _score(value, field)


def _validate_resource_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or len(value) > len(_KNOWN_METADATA):
        raise BenchmarkError(f"{field} must be a bounded array")
    output: list[str] = []
    for index, resource in enumerate(value):
        resource = _text(resource, f"{field}[{index}]")
        if resource not in _KNOWN_METADATA:
            raise BenchmarkError(f"{field} contains an unknown resource")
        if resource in output:
            raise BenchmarkError(f"{field} contains duplicate resources")
        output.append(resource)
    canonical = [resource for resource in _KNOWN_METADATA if resource in output]
    if output != canonical:
        raise BenchmarkError(f"{field} must use canonical resource order")
    return output


def validate_benchmark(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the exact public benchmark envelope before it is shared.

    Benchmark files are intentionally data-only.  Unknown fields are rejected
    so a future exporter cannot accidentally publish repository identities,
    people, dependency names, finding text, or raw provider records.
    """
    if not isinstance(summary, Mapping):
        raise BenchmarkError("benchmark summary must be an object")
    if set(summary) != _SUMMARY_KEYS:
        raise BenchmarkError("benchmark summary fields are invalid")
    if summary.get("schema_version") != BENCHMARK_SCHEMA_VERSION:
        raise BenchmarkError("unsupported benchmark summary schema version")
    if summary.get("scope") != "privacy-preserving-summary":
        raise BenchmarkError("benchmark summary scope is invalid")
    if summary.get("not_a_ranking") is not True:
        raise BenchmarkError("benchmark summary must declare not_a_ranking=true")
    _text(summary.get("rule_version"), "rule_version")

    tool = summary.get("tool")
    if tool is not None:
        if not isinstance(tool, Mapping) or set(tool) != _TOOL_KEYS:
            raise BenchmarkError("benchmark tool metadata is invalid")
        if tool.get("name") != "Maintainer-Zero":
            raise BenchmarkError("benchmark tool name is invalid")
        _text(tool.get("version"), "tool.version")

    privacy = summary.get("privacy")
    if not isinstance(privacy, Mapping) or set(privacy) != _PRIVACY_KEYS:
        raise BenchmarkError("benchmark privacy declaration is invalid")
    expected_privacy = {
        "repository_identity": "omitted",
        "contributor_identity": "omitted",
        "raw_records": "omitted",
        "repository_content_upload": False,
    }
    if dict(privacy) != expected_privacy:
        raise BenchmarkError("benchmark privacy declaration must omit identities and raw records")

    scenarios = summary.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) > _MAX_SCENARIOS:
        raise BenchmarkError("benchmark summary scenarios must be a bounded array")
    seen: set[str] = set()
    scores: list[int] = []
    previous_id: str | None = None
    for index, item in enumerate(scenarios):
        if not isinstance(item, Mapping) or set(item) != _SCENARIO_KEYS:
            raise BenchmarkError(f"summary scenario {index} fields are invalid")
        scenario = _text(item.get("id"), f"summary scenario {index} id")
        if scenario not in _KNOWN_SCENARIOS:
            raise BenchmarkError("benchmark summary scenario is not reviewed")
        if scenario in seen:
            raise BenchmarkError("benchmark summary contains duplicate scenarios")
        if previous_id is not None and scenario.casefold() < previous_id.casefold():
            raise BenchmarkError("benchmark summary scenarios must be sorted")
        previous_id = scenario
        seen.add(scenario)
        scores.append(_integer_score(item.get("score"), f"summary scenario {index} score"))
        confidence = item.get("confidence")
        if not isinstance(confidence, str) or confidence not in _CONFIDENCES:
            raise BenchmarkError(f"summary scenario {index} confidence is invalid")
        counts = item.get("finding_counts")
        if not isinstance(counts, Mapping) or set(counts) != set(_SEVERITIES):
            raise BenchmarkError(f"summary scenario {index} finding_counts are invalid")
        for severity in _SEVERITIES:
            _bounded_count(counts[severity], f"summary scenario {index} finding_counts.{severity}")

    overall = summary.get("overall_score")
    if overall is not None:
        expected_overall = round(sum(scores) / len(scores)) if scores else None
        if _integer_score(overall, "overall_score") != expected_overall:
            raise BenchmarkError("benchmark overall_score does not match scenario scores")
    elif scores:
        raise BenchmarkError("benchmark overall_score is required when scenarios are present")

    metadata = summary.get("metadata")
    if not isinstance(metadata, Mapping) or set(metadata) != _METADATA_KEYS:
        raise BenchmarkError("benchmark metadata declaration is invalid")
    available = _validate_resource_list(metadata["available_resources"], "metadata.available_resources")
    unknown = _validate_resource_list(metadata["unknown_resources"], "metadata.unknown_resources")
    if set(available) & set(unknown) or set(available) | set(unknown) != set(_KNOWN_METADATA):
        raise BenchmarkError("benchmark metadata resources must partition known resources")
    return dict(summary)


def render_benchmark_text(summary: Mapping[str, Any]) -> str:
    """Render a compact text view that preserves the same privacy omissions."""
    # This public helper may be called independently of ``build_benchmark``.
    # Validate every interpolated value so an untrusted mapping cannot inject
    # control characters or arbitrary fields into a shareable text artifact.
    if not isinstance(summary, Mapping):
        raise BenchmarkError("benchmark summary must be an object")
    rule_version = _text(summary.get("rule_version"), "rule_version")
    overall = summary.get("overall_score")
    overall_score = None if overall is None else _score(overall, "overall_score")
    scenarios = summary.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) > _MAX_SCENARIOS:
        raise BenchmarkError("benchmark summary scenarios must be a bounded array")
    validated_scenarios: list[tuple[str, int, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(scenarios):
        if not isinstance(item, Mapping):
            raise BenchmarkError(f"summary scenario {index} must be an object")
        scenario = _text(item.get("id"), f"summary scenario {index} id")
        if scenario not in _KNOWN_SCENARIOS:
            raise BenchmarkError("benchmark summary scenario is not reviewed")
        key = scenario.casefold()
        if key in seen:
            raise BenchmarkError("benchmark summary contains duplicate scenarios")
        seen.add(key)
        score = _score(item.get("score"), f"summary scenario {index} score")
        confidence = item.get("confidence")
        if not isinstance(confidence, str) or confidence not in _CONFIDENCES:
            raise BenchmarkError(f"summary scenario {index} confidence is invalid")
        validated_scenarios.append((scenario, score, confidence))
    lines = [
        "Maintainer-Zero privacy-preserving benchmark summary",
        f"Rule version: {rule_version}",
        f"Overall score: {overall_score if overall_score is not None else 'unknown'}",
        "Scope: privacy-preserving-summary (not a ranking)",
        "Repository identity and raw records: omitted",
    ]
    for scenario, score, confidence in validated_scenarios:
        lines.append(f"  {scenario}: {score}/100 ({confidence})")
    return "\n".join(lines) + "\n"


__all__ = [
    "BENCHMARK_SCHEMA_VERSION", "MAX_BENCHMARK_BYTES", "BenchmarkError",
    "build_benchmark", "load_benchmark", "render_benchmark_text",
    "validate_benchmark",
]
