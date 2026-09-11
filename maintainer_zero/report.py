from __future__ import annotations

import html
import json
from pathlib import Path
from .models import DrillResult, RepoSnapshot


def _metadata_section(metadata_summary: dict | None) -> list[str]:
    if metadata_summary is None:
        return []
    fields = metadata_summary.get("fields", {})
    unknown = metadata_summary.get("unknown", [])
    lines = ["## GitHub metadata", "", "Read-only metadata was supplied by an external snapshot; unavailable fields remain unknown.", ""]
    lines.extend(f"- **{key}**: {value if value is not None else 'unknown'}" for key, value in fields.items())
    if unknown:
        lines.extend(["", f"Unknown fields: `{', '.join(unknown)}`"] )
    return lines + [""]

def render_markdown(repo: RepoSnapshot, results: list[DrillResult], metadata_summary: dict | None = None) -> str:
    lines = [f"# OSS Continuity Report: {repo.name}", "", "- **Rule version:** `0.2`", f"- Commits analyzed: **{repo.commits}**", f"- Contributors: **{len(repo.contributors)}**", f"- Dependencies found: **{len(repo.dependencies)}**", f"- Workflows found: **{len(repo.workflows)}**", "", "> This is an explainable heuristic drill, not a security certification.", ""]
    for result in results:
        lines += [f"## {result.scenario} — {result.score}/100", "", f"Confidence: `{result.confidence}`", "", "### Metrics", ""]
        lines.extend(f"- **{key}**: {value}" for key, value in result.metrics.items())
        lines += ["", "### Findings", ""]
        lines.extend(f"- **{f.severity.upper()} — {f.title}** (`{f.finding_id or 'unclassified'}`): {f.detail} *Action:* {f.action}" for f in result.findings)
        lines += ["", "### Timeline", "", "```mermaid", "timeline", "    title Incident drill"]
        lines.extend(f"    Day {e['day']} : {e['event']} : {e['impact']}" for e in result.timeline)
        lines += ["```", ""]
    lines += _metadata_section(metadata_summary)
    lines += ["## Suggested next steps", "", "1. Assign a backup owner for every critical path.", "2. Test a clean checkout and local release procedure.", "3. Re-run this drill monthly and track score changes in Git."]
    return "\n".join(lines) + "\n"

def write_report(out: Path, repo: RepoSnapshot, results: list[DrillResult], metadata_summary: dict | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "rule_version": "0.2", "repository": repo.to_dict(), "results": [r.to_dict() for r in results]}
    if metadata_summary is not None:
        payload["github_metadata"] = metadata_summary
    (out / "continuity.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown = render_markdown(repo, results, metadata_summary)
    (out / "report.md").write_text(markdown, encoding="utf-8")
    body = html.escape(markdown).replace("\n", "<br>")
    (out / "report.html").write_text(f"<!doctype html><meta charset='utf-8'><title>Continuity Report</title><style>body{{font:16px system-ui;max-width:1000px;margin:40px auto;line-height:1.5}}</style><pre>{body}</pre>", encoding="utf-8")
