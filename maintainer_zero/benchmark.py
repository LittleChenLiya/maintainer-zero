"""Build privacy-preserving, non-ranking benchmark summaries from reports."""
from __future__ import annotations

import math
from typing import Any, Mapping

BENCHMARK_SCHEMA_VERSION = 1
_SEVERITIES = ("high", "medium", "low", "info", "unknown")
_CONFIDENCES = frozenset({"high", "medium", "low", "unknown"})
_KNOWN_SCENARIOS = frozenset({"maintainer-zero", "dependency-yanked", "ci-outage"})
_KNOWN_METADATA = ("repository", "issues", "pull_requests", "reviews", "releases")
_MAX_SCENARIOS = 128
_MAX_TEXT = 128


class BenchmarkError(ValueError):
    """Raised when a report cannot be reduced to a safe benchmark summary."""


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > _MAX_TEXT:
        raise BenchmarkError(f"{field} must be a bounded non-empty string")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise BenchmarkError(f"{field} contains control characters")
    return value


def _score(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise BenchmarkError(f"{field} must be a finite score")
    score = round(float(value))
    if not 0 <= score <= 100:
        raise BenchmarkError(f"{field} must be between 0 and 100")
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


def render_benchmark_text(summary: Mapping[str, Any]) -> str:
    """Render a compact text view that preserves the same privacy omissions."""
    lines = [
        "Maintainer-Zero privacy-preserving benchmark summary",
        f"Rule version: {summary['rule_version']}",
        f"Overall score: {summary['overall_score'] if summary['overall_score'] is not None else 'unknown'}",
        "Scope: privacy-preserving-summary (not a ranking)",
        "Repository identity and raw records: omitted",
    ]
    for item in summary["scenarios"]:
        lines.append(f"  {item['id']}: {item['score']}/100 ({item['confidence']})")
    return "\n".join(lines) + "\n"


__all__ = ["BENCHMARK_SCHEMA_VERSION", "BenchmarkError", "build_benchmark", "render_benchmark_text"]
