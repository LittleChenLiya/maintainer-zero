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


__all__ = ["BENCHMARK_SCHEMA_VERSION", "BenchmarkError", "build_benchmark", "render_benchmark_text"]
