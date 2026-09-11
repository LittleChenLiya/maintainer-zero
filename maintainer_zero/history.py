"""Local, same-repository continuity report history and trend summaries.

History is intentionally a small JSON document rather than a database.  It stores
scores and finding counts, never raw repository records, and refuses to mix
reports whose repository identity does not match the history owner.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

HISTORY_SCHEMA_VERSION = 1
MAX_HISTORY_ENTRIES = 1_000


class HistoryError(ValueError):
    """Raised when a history file is malformed or belongs to another repository."""


def _repository(report: Mapping[str, Any]) -> dict[str, str]:
    repository = report.get("repository")
    if not isinstance(repository, Mapping):
        raise HistoryError("continuity report repository must be an object")
    name, path = repository.get("name"), repository.get("path")
    if not isinstance(name, str) or not name.strip() or not isinstance(path, str) or not path.strip():
        raise HistoryError("continuity report repository name and path are required")
    return {"name": name, "path": path}


def _identity(repository: Mapping[str, str]) -> str:
    value = f"{repository['name']}\0{repository['path']}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:16]


def _score(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value))


def summarize_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Extract trend-safe aggregates from a full continuity report."""
    repository = _repository(report)
    results = report.get("results")
    if not isinstance(results, list):
        raise HistoryError("continuity report results must be an array")
    scenarios: dict[str, int | None] = {}
    finding_counts: dict[str, int] = {}
    high_risk = 0
    scores: list[int] = []
    for result in results:
        if not isinstance(result, Mapping) or not isinstance(result.get("scenario"), str):
            continue
        score = _score(result.get("score"))
        scenarios[result["scenario"]] = score
        if score is not None:
            scores.append(score)
        findings = result.get("findings")
        finding_counts[result["scenario"]] = len(findings) if isinstance(findings, list) else 0
        if isinstance(findings, list):
            high_risk += sum(1 for finding in findings if isinstance(finding, Mapping) and str(finding.get("severity", "")).lower() == "high")
    return {
        "repository": repository,
        "repository_id": _identity(repository),
        "rule_version": report.get("rule_version"),
        "overall_score": round(sum(scores) / len(scores)) if scores else None,
        "scenarios": scenarios,
        "finding_counts": finding_counts,
        "high_risk_findings": high_risk,
    }


def _validate_history(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != HISTORY_SCHEMA_VERSION:
        raise HistoryError("unsupported history schema_version")
    repository = payload.get("repository")
    if not isinstance(repository, Mapping) or not isinstance(repository.get("name"), str) or not isinstance(repository.get("path"), str):
        raise HistoryError("history repository must include name and path")
    entries = payload.get("entries")
    if not isinstance(entries, list) or len(entries) > MAX_HISTORY_ENTRIES:
        raise HistoryError(f"history entries must be an array of at most {MAX_HISTORY_ENTRIES} items")
    for entry in entries:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("recorded_at"), str) or not isinstance(entry.get("overall_score"), (int, type(None))):
            raise HistoryError("history entries are malformed")


def load_history(path: str | Path) -> dict[str, Any]:
    history_path = Path(path)
    try:
        payload = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HistoryError(f"Invalid continuity history: {history_path}") from exc
    if not isinstance(payload, dict):
        raise HistoryError("continuity history must be a JSON object")
    _validate_history(payload)
    return payload


def append_history(path: str | Path, report: Mapping[str, Any], *, recorded_at: str | None = None) -> dict[str, Any]:
    """Append a compact report aggregate and return the trend summary."""
    path = Path(path)
    summary = summarize_report(report)
    if path.exists():
        payload = load_history(path)
        owner = payload["repository"]
        if owner.get("name") != summary["repository"]["name"] or owner.get("path") != summary["repository"]["path"]:
            raise HistoryError("history belongs to a different repository")
    else:
        payload = {"schema_version": HISTORY_SCHEMA_VERSION, "repository": summary["repository"], "repository_id": summary["repository_id"], "entries": []}
    entries = payload["entries"]
    if len(entries) >= MAX_HISTORY_ENTRIES:
        raise HistoryError(f"history entries limit reached ({MAX_HISTORY_ENTRIES})")
    entry = {
        "recorded_at": recorded_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        **{key: summary[key] for key in ("rule_version", "overall_score", "scenarios", "finding_counts", "high_risk_findings")},
    }
    entries.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return trend_summary(payload)


def trend_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return latest and first-to-latest changes for one repository only."""
    _validate_history(payload)
    entries = list(payload["entries"])
    latest = entries[-1] if entries else None
    previous = entries[-2] if len(entries) > 1 else None
    first = entries[0] if entries else None
    def delta(left: Mapping[str, Any] | None, right: Mapping[str, Any] | None, key: str) -> int | None:
        old, new = (left or {}).get(key), (right or {}).get(key)
        return new - old if isinstance(old, int) and isinstance(new, int) else None
    scenario_delta: dict[str, int] = {}
    if first and latest:
        names = set((first.get("scenarios") or {})) | set((latest.get("scenarios") or {}))
        for name in sorted(names):
            old, new = (first.get("scenarios") or {}).get(name), (latest.get("scenarios") or {}).get(name)
            if isinstance(old, int) and isinstance(new, int):
                scenario_delta[name] = new - old
    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "repository": payload["repository"],
        "repository_id": payload.get("repository_id") or _identity(payload["repository"]),
        "runs": len(entries),
        "latest": latest,
        "delta_since_previous": delta(previous, latest, "overall_score"),
        "delta_since_first": delta(first, latest, "overall_score"),
        "scenario_delta_since_first": scenario_delta,
    }


__all__ = ["HISTORY_SCHEMA_VERSION", "HistoryError", "append_history", "load_history", "summarize_report", "trend_summary"]
