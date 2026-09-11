from __future__ import annotations

import html
import json
from pathlib import Path
from .models import DrillResult, RepoSnapshot

def render_markdown(repo: RepoSnapshot, results: list[DrillResult]) -> str:
    lines = [f"# OSS Continuity Report: {repo.name}", "", f"- Commits analyzed: **{repo.commits}**", f"- Contributors: **{len(repo.contributors)}**", f"- Dependencies found: **{len(repo.dependencies)}**", f"- Workflows found: **{len(repo.workflows)}**", "", "> This is an explainable heuristic drill, not a security certification.", ""]
    for result in results:
        lines += [f"## {result.scenario} — {result.score}/100", "", f"Confidence: `{result.confidence}`", "", "### Metrics", ""]
        lines.extend(f"- **{key}**: {value}" for key, value in result.metrics.items())
        lines += ["", "### Findings", ""]
        lines.extend(f"- **{f.severity.upper()} — {f.title}**: {f.detail} *Action:* {f.action}" for f in result.findings)
        lines += ["", "### Timeline", "", "```mermaid", "timeline", "    title Incident drill"]
        lines.extend(f"    Day {e['day']} : {e['event']} : {e['impact']}" for e in result.timeline)
        lines += ["```", ""]
    lines += ["## Suggested next steps", "", "1. Assign a backup owner for every critical path.", "2. Test a clean checkout and local release procedure.", "3. Re-run this drill monthly and track score changes in Git."]
    return "\n".join(lines) + "\n"

def write_report(out: Path, repo: RepoSnapshot, results: list[DrillResult]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    payload = {"repository": repo.to_dict(), "results": [r.to_dict() for r in results]}
    (out / "continuity.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown = render_markdown(repo, results)
    (out / "report.md").write_text(markdown, encoding="utf-8")
    body = html.escape(markdown).replace("\n", "<br>")
    (out / "report.html").write_text(f"<!doctype html><meta charset='utf-8'><title>Continuity Report</title><style>body{{font:16px system-ui;max-width:1000px;margin:40px auto;line-height:1.5}}</style><pre>{body}</pre>", encoding="utf-8")
