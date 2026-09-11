from __future__ import annotations

import json
from pathlib import Path
from typing import Any

class BaselineError(ValueError):
    pass

def load_report(path: str | Path) -> dict[str, Any]:
    source = Path(path).resolve()
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BaselineError(f"Invalid baseline report: {source}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise BaselineError(f"Baseline report has no results list: {source}")
    return data

def compare_reports(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    current_results = {str(x.get("scenario")): x for x in current.get("results", []) if isinstance(x, dict) and x.get("scenario")}
    baseline_results = {str(x.get("scenario")): x for x in baseline.get("results", []) if isinstance(x, dict) and x.get("scenario")}
    changes: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []
    new_high: list[dict[str, Any]] = []
    for scenario in sorted(set(current_results) | set(baseline_results)):
        now = current_results.get(scenario)
        old = baseline_results.get(scenario)
        if now is None:
            changes.append({"scenario": scenario, "status": "removed", "score_delta": None})
            continue
        if old is None:
            changes.append({"scenario": scenario, "status": "new", "score": now.get("score")})
        else:
            a, b = now.get("score"), old.get("score")
            delta = a - b if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
            status = "regressed" if isinstance(delta, (int, float)) and delta < 0 else "improved" if isinstance(delta, (int, float)) and delta > 0 else "unchanged"
            item = {"scenario": scenario, "status": status, "baseline_score": b, "score": a, "score_delta": delta}
            changes.append(item)
            if status == "regressed":
                regressions.append(item)
        old_ids = {str(f.get("finding_id")) for f in (old or {}).get("findings", []) if isinstance(f, dict) and f.get("finding_id")}
        for finding in now.get("findings", []):
            if isinstance(finding, dict) and finding.get("severity") == "high" and finding.get("finding_id") and str(finding["finding_id"]) not in old_ids:
                new_high.append({"scenario": scenario, "finding_id": finding["finding_id"], "title": finding.get("title")})
    status = "regressed" if regressions or new_high else "changed" if any(x.get("status") != "unchanged" for x in changes) else "unchanged"
    return {"schema_version": current.get("schema_version"), "status": status, "scenarios": changes, "score_regressions": regressions, "new_high_findings": new_high}
