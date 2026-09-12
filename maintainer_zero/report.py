from __future__ import annotations

import html
import json
import os
import re
import tempfile
from pathlib import Path
from .models import DrillResult, RepoSnapshot

_SECRET_RE = re.compile(
    r"(?i)(\b(?:token|secret|password|passwd|api[_-]?key|authorization)\b\s*[:=]\s*)([\"']?)([^\"'\s,;}]+)\2"
)
_SECRET_KEY_RE = re.compile(r"(?i)^(?:token|secret|password|passwd|api[_-]?key|authorization)$")


def _safe_text(value: object) -> str:
    """Sanitize repository-controlled text before it enters a shareable report."""
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = "".join(char if char.isprintable() or char == "\t" else " � " for char in text).strip()
    return _SECRET_RE.sub(lambda match: f"{match.group(1)}[REDACTED]", text)


def _safe_value(value: object) -> object:
    if isinstance(value, str):
        safe = _safe_text(value)
        return safe if safe == "<local-repository>" else safe.replace("<", "&lt;").replace(">", "&gt;")
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            safe_key = _safe_text(key)
            sanitized[safe_key] = "[REDACTED]" if _SECRET_KEY_RE.fullmatch(safe_key.strip()) else _safe_value(item)
        return sanitized
    return value


def _display(value: object) -> str:
    safe = _safe_value(value)
    if isinstance(safe, (dict, list)):
        return json.dumps(safe, ensure_ascii=False, sort_keys=True)
    rendered = json.dumps(safe, ensure_ascii=False, sort_keys=True) if isinstance(safe, (dict, list)) else str(safe)
    return rendered.replace("<", "&lt;").replace(">", "&gt;")


def _markdown_text(value: object) -> str:
    return _safe_text(value).replace("<", "&lt;").replace(">", "&gt;")

def _atomic_write_text(path: str | Path, content: str) -> None:
    """Atomically replace one report artifact in its output directory."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _metadata_section(metadata_summary: dict | None) -> list[str]:
    if metadata_summary is None:
        return []
    fields = metadata_summary.get("fields", {})
    unknown = metadata_summary.get("unknown", [])
    partial = metadata_summary.get("partial", [])
    lines = ["## GitHub metadata", "", "Read-only metadata was supplied by an external snapshot; unavailable fields remain unknown.", ""]
    lines.extend(f"- **{_markdown_text(key)}**: {_display(value) if value is not None else 'unknown'}" for key, value in fields.items())
    if unknown:
        lines.extend(["", f"Unknown fields: `{', '.join(unknown)}`"] )
    if partial:
        lines.extend(["", f"Partially collected fields (page/item limit): `{', '.join(partial)}`; counts are not complete."])
    return lines + [""]

def render_markdown(repo: RepoSnapshot, results: list[DrillResult], metadata_summary: dict | None = None) -> str:
    lines = [f"# OSS Continuity Report: {_markdown_text(repo.name)}", "", "- **Rule version:** `0.2`", f"- Commits analyzed: **{repo.commits}**", f"- Contributors: **{len(repo.contributors)}**", f"- Dependencies found: **{len(repo.dependencies)}**", f"- Workflows found: **{len(repo.workflows)}**", "", "> This is an explainable heuristic drill, not a security certification.", ""]
    for result in results:
        lines += [f"## {_markdown_text(result.scenario)} — {result.score}/100", "", f"Confidence: `{_markdown_text(result.confidence)}`", "", "### Metrics", ""]
        lines.extend(f"- **{_markdown_text(key)}**: {_display(value)}" for key, value in result.metrics.items())
        lines += ["", "### Findings", ""]
        lines.extend(f"- **{_markdown_text(f.severity).upper()} — {_markdown_text(f.title)}** (`{_markdown_text(f.finding_id or 'unclassified')}`): {_markdown_text(f.detail)} *Action:* {_markdown_text(f.action)}" for f in result.findings)
        lines += ["", "### Timeline", "", "```mermaid", "timeline", "    title Incident drill"]
        lines.extend(f"    Day {e['day']} : {_markdown_text(e['event'])} : {_markdown_text(e['impact'])}" for e in result.timeline)
        lines += ["```", ""]
    lines += _metadata_section(metadata_summary)
    lines += ["## Suggested next steps", "", "1. Assign a backup owner for every critical path.", "2. Test a clean checkout and local release procedure.", "3. Re-run this drill monthly and track score changes in Git."]
    return "\n".join(lines) + "\n"

def write_report(out: Path, repo: RepoSnapshot, results: list[DrillResult], metadata_summary: dict | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    payload = _safe_value({"schema_version": 1, "rule_version": "0.2", "repository": repo.to_dict(), "results": [r.to_dict() for r in results]})
    if metadata_summary is not None:
        payload["github_metadata"] = _safe_value(metadata_summary)
    _atomic_write_text(out / "continuity.json", json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    markdown = render_markdown(repo, results, metadata_summary)
    _atomic_write_text(out / "report.md", markdown)
    body = html.escape(markdown).replace("\n", "<br>")
    _atomic_write_text(out / "report.html", f"<!doctype html><meta charset='utf-8'><title>Continuity Report</title><style>body{{font:16px system-ui;max-width:1000px;margin:40px auto;line-height:1.5}}</style><pre>{body}</pre>")
