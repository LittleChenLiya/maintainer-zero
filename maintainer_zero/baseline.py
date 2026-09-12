"""Deterministic comparison of versioned continuity reports."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Mapping

REPORT_SCHEMA_VERSION = 1
MAX_REPORT_BYTES = 8 * 1024 * 1024
EXPECTED_REPOSITORY_FIELDS = ("commits", "contributors", "dependencies", "workflows", "codeowners", "release_files")


class BaselineError(ValueError):
    """Raised when a baseline or comparison report is unusable."""


def _link_like(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _safe_report_file(path: Path) -> tuple[Path, os.stat_result]:
    target = Path(os.path.abspath(path))
    current = Path(target.anchor) if target.anchor else Path()
    parts = target.parts[1:] if target.anchor else target.parts
    for part in parts[:-1]:
        current /= part
        try:
            info = current.lstat()
        except OSError as exc:
            raise BaselineError(f"cannot inspect report parent: {current}") from exc
        if _link_like(info) or not stat.S_ISDIR(info.st_mode):
            raise BaselineError("report parent must be a real directory")
    try:
        info = target.lstat()
    except OSError as exc:
        raise BaselineError(f"cannot inspect continuity report: {target}") from exc
    if _link_like(info) or not stat.S_ISREG(info.st_mode):
        raise BaselineError("continuity report must be a regular file")
    return target, info


def load_report(path: str | Path) -> dict[str, Any]:
    report_path, info = _safe_report_file(Path(path))
    if info.st_size > MAX_REPORT_BYTES:
        raise BaselineError("continuity report exceeds size limit")
    try:
        with report_path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if _link_like(opened) or not stat.S_ISREG(opened.st_mode):
                raise BaselineError("continuity report descriptor is not a regular file")
            if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                raise BaselineError("continuity report changed before reading")
            raw = handle.read(MAX_REPORT_BYTES + 1)
        if len(raw) > MAX_REPORT_BYTES:
            raise BaselineError("continuity report exceeds size limit")
        after = report_path.lstat()
        if (after.st_dev, after.st_ino) != (info.st_dev, info.st_ino) or after.st_size != info.st_size:
            raise BaselineError("continuity report changed during reading")
        if getattr(after, "st_mtime_ns", None) != getattr(info, "st_mtime_ns", None):
            raise BaselineError("continuity report changed during reading")
        payload = json.loads(raw.decode("utf-8"))
    except BaselineError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BaselineError(f"Invalid continuity report: {report_path}") from exc
    if not isinstance(payload, dict):
        raise BaselineError("continuity report must be a JSON object")
    _validate_report(payload)
    return payload


def _validate_report(report: Mapping[str, Any]) -> None:
    schema = report.get("schema_version")
    if isinstance(schema, bool) or not isinstance(schema, int) or schema < 1:
        raise BaselineError("continuity report schema_version must be a positive integer")
    if schema > REPORT_SCHEMA_VERSION:
        raise BaselineError(f"unsupported continuity report schema_version: {schema}")
    rule = report.get("rule_version")
    if not isinstance(rule, str) or not rule.strip():
        raise BaselineError("continuity report rule_version must be a non-empty string")
    if not isinstance(report.get("repository"), Mapping):
        raise BaselineError("continuity report repository must be an object")
    if not isinstance(report.get("results"), list):
        raise BaselineError("continuity report results must be an array")
    tool = report.get("tool")
    if tool is not None and (
        not isinstance(tool, Mapping)
        or tool.get("name") != "Maintainer-Zero"
        or not isinstance(tool.get("version"), str)
        or not tool["version"].strip()
    ):
        raise BaselineError("continuity report tool metadata is invalid")


def _results(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    for item in report.get("results", []):
        if isinstance(item, Mapping) and isinstance(item.get("scenario"), str) and item["scenario"]:
            output.setdefault(item["scenario"], item)
    return output


def _score(result: Mapping[str, Any] | None) -> int | None:
    value = result.get("score") if result is not None else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value))


def _finding_key(finding: Mapping[str, Any]) -> str:
    finding_id = finding.get("finding_id")
    return finding_id if isinstance(finding_id, str) and finding_id else f"legacy:{finding.get('severity', 'unknown')}:{finding.get('title', 'untitled')}"


def _findings(result: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    if result is None or not isinstance(result.get("findings"), list):
        return output
    for finding in result["findings"]:
        if isinstance(finding, Mapping):
            output.setdefault(_finding_key(finding), finding)
    return output


def _coverage(report: Mapping[str, Any]) -> dict[str, Any]:
    repository = report["repository"]
    fields = {name: name in repository for name in EXPECTED_REPOSITORY_FIELDS}
    covered = sum(fields.values())
    return {"covered_fields": covered, "total_fields": len(fields), "percent": round(covered / len(fields) * 100), "fields": fields}


def compare_reports(baseline: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    _validate_report(baseline)
    _validate_report(current)
    if baseline["rule_version"] != current["rule_version"]:
        raise BaselineError("cannot compare reports produced by different rule versions")
    baseline_tool = baseline.get("tool")
    current_tool = current.get("tool")
    if baseline_tool is not None and current_tool is not None and baseline_tool["version"] != current_tool["version"]:
        raise BaselineError("cannot compare reports produced by different tool versions")
    old_results, new_results = _results(baseline), _results(current)
    scenarios: list[dict[str, Any]] = []
    added_findings: list[dict[str, Any]] = []
    resolved_findings: list[dict[str, Any]] = []
    new_high_risk: list[dict[str, Any]] = []
    for scenario in sorted(set(old_results) | set(new_results)):
        old_result, new_result = old_results.get(scenario), new_results.get(scenario)
        old_score, new_score = _score(old_result), _score(new_result)
        delta = new_score - old_score if old_score is not None and new_score is not None else None
        old_findings, new_findings = _findings(old_result), _findings(new_result)
        added_ids, removed_ids = sorted(set(new_findings) - set(old_findings)), sorted(set(old_findings) - set(new_findings))
        for finding_id in added_ids:
            entry = {"scenario": scenario, "finding_id": finding_id, "finding": dict(new_findings[finding_id])}
            added_findings.append(entry)
            if str(new_findings[finding_id].get("severity", "")).lower() == "high":
                new_high_risk.append(entry)
        # A stable finding can become more dangerous without changing its ID.
        # Treat a non-high -> high severity transition as a newly introduced
        # high-risk condition so explicit high-risk gates cannot miss it.
        for finding_id in sorted(set(old_findings) & set(new_findings)):
            old_severity = str(old_findings[finding_id].get("severity", "")).lower()
            new_severity = str(new_findings[finding_id].get("severity", "")).lower()
            if new_severity == "high" and old_severity != "high":
                new_high_risk.append(
                    {
                        "scenario": scenario,
                        "finding_id": finding_id,
                        "finding": dict(new_findings[finding_id]),
                        "previous_severity": old_severity or "unknown",
                        "change": "severity_escalation",
                    }
                )
        resolved_findings.extend({"scenario": scenario, "finding_id": finding_id} for finding_id in removed_ids)
        status = "added" if old_result is None else "removed" if new_result is None else "improved" if delta is not None and delta > 0 else "regressed" if delta is not None and delta < 0 else "unchanged"
        scenarios.append({"scenario": scenario, "baseline_score": old_score, "current_score": new_score, "delta": delta, "score_delta": delta, "added_finding_ids": added_ids, "resolved_finding_ids": removed_ids, "status": status})
    old_scores = [value for value in (_score(result) for result in old_results.values()) if value is not None]
    new_scores = [value for value in (_score(result) for result in new_results.values()) if value is not None]
    old_overall = round(sum(old_scores) / len(old_scores)) if old_scores else None
    new_overall = round(sum(new_scores) / len(new_scores)) if new_scores else None
    score_decreased = any(item["delta"] is not None and item["delta"] < 0 for item in scenarios)
    high_risk = bool(new_high_risk)
    status = "regressed" if score_decreased or high_risk else "changed" if any(item["status"] != "unchanged" for item in scenarios) else "unchanged"
    old_coverage, new_coverage = _coverage(baseline), _coverage(current)
    return {"schema_version": REPORT_SCHEMA_VERSION, "rule_version": current.get("rule_version"), "baseline_rule_version": baseline.get("rule_version"), "overall": {"baseline_score": old_overall, "current_score": new_overall, "delta": new_overall - old_overall if old_overall is not None and new_overall is not None else None}, "scenarios": scenarios, "findings": {"added": added_findings, "resolved": resolved_findings, "new_high_risk": new_high_risk}, "coverage": {"baseline": old_coverage, "current": new_coverage, "delta": new_coverage["percent"] - old_coverage["percent"]}, "gates": {"score_decreased": score_decreased, "new_high_risk": high_risk}, "status": status, "score_regressions": [item for item in scenarios if item["status"] == "regressed"], "new_high_findings": new_high_risk}


def gate_failed(comparison: Mapping[str, Any], *, fail_on_score_decrease: bool = False, fail_on_new_high_risk: bool = False) -> bool:
    gates = comparison.get("gates")
    if not isinstance(gates, Mapping):
        raise BaselineError("comparison gates are missing")
    return bool((fail_on_score_decrease and gates.get("score_decreased")) or (fail_on_new_high_risk and gates.get("new_high_risk")))


__all__ = ["BaselineError", "REPORT_SCHEMA_VERSION", "compare_reports", "gate_failed", "load_report"]
