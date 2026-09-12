from __future__ import annotations

import html
import json
import os
import stat
import re
import tempfile
from pathlib import Path
from .models import DrillResult, RepoSnapshot
from .privacy import validate_snapshot_projection
from . import __version__

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
    target = _safe_output_file(path)
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


def _is_link_like(info: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & reparse_flag)


def _safe_output_directory(path: str | Path) -> Path:
    target = Path(path)
    if not target.is_absolute():
        target = Path.cwd() / target
    current = Path(target.anchor) if target.anchor else Path()
    parts = target.parts[1:] if target.anchor else target.parts
    for part in parts:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            current.mkdir()
            info = current.lstat()
        if _is_link_like(info):
            raise ValueError(f"report output path may not contain a symlink or reparse point: {current}")
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"report output path is not a directory: {current}")
    return target


def _safe_output_file(path: str | Path) -> Path:
    target = Path(path)
    if not target.is_absolute():
        target = Path.cwd() / target
    parent = _safe_output_directory(target.parent)
    target = parent / target.name
    if os.path.lexists(target):
        info = target.lstat()
        if _is_link_like(info) or not stat.S_ISREG(info.st_mode):
            raise ValueError(f"report output file must be a regular file: {target}")
    return target


def _preflight_report_targets(out: Path) -> None:
    """Validate every report target before replacing any artifact."""
    for filename in ("continuity.json", "report.md", "report.html"):
        _safe_output_file(out / filename)


def _report_backup_path(directory: Path, filename: str) -> Path:
    handle = tempfile.NamedTemporaryFile(mode="wb", dir=directory, prefix=f".{filename}.", suffix=".bak", delete=False)
    backup = Path(handle.name)
    handle.close()
    backup.unlink(missing_ok=True)
    return backup


def _atomic_write_report_set(out: Path, artefacts: dict[str, str]) -> None:
    """Replace the report generation as one rollback-capable set."""
    staged: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    replaced: list[Path] = []
    try:
        for filename, content in artefacts.items():
            target = out / filename
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", dir=out,
                prefix=f".{target.name}.", suffix=".tmp", delete=False
            ) as handle:
                staged[target] = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())

        _preflight_report_targets(out)
        for target, temporary in list(staged.items()):
            if os.path.lexists(target):
                backup = _report_backup_path(out, target.name)
                os.replace(target, backup)
                backups[target] = backup
            os.replace(temporary, target)
            replaced.append(target)
            staged.pop(target, None)
    except BaseException:
        for target in reversed(replaced):
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
        for target, backup in backups.items():
            if backup.exists() or os.path.lexists(backup):
                try:
                    os.rename(backup, target)
                except OSError:
                    pass
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
        for backup in backups.values():
            backup.unlink(missing_ok=True)


def _metadata_section(metadata_summary: dict | None) -> list[str]:
    if metadata_summary is None:
        return []
    fields = metadata_summary.get("fields", {})
    unknown = metadata_summary.get("unknown", [])
    partial = metadata_summary.get("partial", [])
    lines = ["## GitHub metadata", "", "Read-only metadata was supplied by an external snapshot; unavailable fields remain unknown. These observations provide context and do not change drill scores.", "", "### Metadata evidence", ""]
    lines.extend(f"- **{_markdown_text(key)}**: {_markdown_text('unknown' if key in unknown or value is None else 'partial' if key in partial else 'observed')} — {_display(value) if value is not None else 'unknown'}" for key, value in sorted(fields.items()))
    if unknown:
        lines.extend(["", f"Unknown fields: `{', '.join(unknown)}`"] )
    if partial:
        lines.extend(["", f"Partially collected fields (page/item limit): `{', '.join(partial)}`; counts are not complete."])
    return lines + [""]


def _metadata_evidence(metadata_summary: dict | None) -> list[dict[str, object]]:
    """Turn the bounded metadata summary into auditable, non-raw observations."""
    if metadata_summary is None:
        return []
    fields = metadata_summary.get("fields", {})
    unknown = set(metadata_summary.get("unknown", []))
    partial = set(metadata_summary.get("partial", []))
    if not isinstance(fields, dict):
        return []
    evidence: list[dict[str, object]] = []
    for key in sorted(fields):
        value = fields[key]
        status = "unknown" if key in unknown or value is None else "partial" if key in partial else "observed"
        observed: object = value if isinstance(value, (str, int, float, bool)) or value is None else "present"
        evidence.append({"source": "github metadata", "field": key, "observed": observed, "status": status})
    return evidence

def _privacy_section(privacy_summary: dict | None) -> list[str]:
    if privacy_summary is None:
        return []
    people = privacy_summary.get("anonymize_people") is True
    repository = privacy_summary.get("anonymize_repository") is True
    people_state = "anonymized" if people else "present"
    repository_state = "anonymized" if repository else "present"
    return [
        "## Privacy boundary", "",
        f"- Contributor and CODEOWNERS identities: **{people_state}**",
        f"- Repository name and path: **{repository_state}**",
        "- Repository content upload: **disabled**",
        "> This summary describes report handling; it does not reproduce the redacted identities or local path.", "",
    ]


def render_markdown(repo: RepoSnapshot, results: list[DrillResult], metadata_summary: dict | None = None, privacy_summary: dict | None = None) -> str:
    privacy_summary = validate_snapshot_projection(repo, privacy_summary)
    lines = [f"# OSS Continuity Report: {_markdown_text(repo.name)}", "", "- **Rule version:** `0.2`", f"- Commits analyzed: **{repo.commits}**", f"- Contributors: **{len(repo.contributors)}**", f"- Dependencies found: **{len(repo.dependencies)}**", f"- Workflows found: **{len(repo.workflows)}**", "", "> This is an explainable heuristic drill, not a security certification.", ""]
    lines.insert(2, "- **Tool version:** " + chr(96) + _markdown_text(__version__) + chr(96))
    for result in results:
        lines += [f"## {_markdown_text(result.scenario)} — {result.score}/100", "", f"Confidence: `{_markdown_text(result.confidence)}`", "", "### Metrics", ""]
        lines.extend(f"- **{_markdown_text(key)}**: {_display(value)}" for key, value in result.metrics.items())
        lines += ["", "### Evidence", ""]
        if result.evidence:
            lines.extend(
                f"- **{_markdown_text(item.source)} / {_markdown_text(item.field)}**: {_display(item.observed)}"
                + (f" — {_markdown_text(item.note)}" if item.note else "")
                for item in result.evidence
            )
        else:
            lines.append("- No structured evidence was supplied by this scenario.")
        lines += ["", "### Findings", ""]
        lines.extend(f"- **{_markdown_text(f.severity).upper()} — {_markdown_text(f.title)}** (`{_markdown_text(f.finding_id or 'unclassified')}`): {_markdown_text(f.detail)} *Action:* {_markdown_text(f.action)}" for f in result.findings)
        lines += ["", "### Timeline", "", "```mermaid", "timeline", "    title Incident drill"]
        lines.extend(f"    Day {e['day']} : {_markdown_text(e['event'])} : {_markdown_text(e['impact'])}" for e in result.timeline)
        lines += ["```", ""]
    lines += _metadata_section(metadata_summary)
    lines += _privacy_section(privacy_summary)
    lines += ["## Suggested next steps", "", "1. Assign a backup owner for every critical path.", "2. Test a clean checkout and local release procedure.", "3. Re-run this drill monthly and track score changes in Git."]
    return "\n".join(lines) + "\n"

def write_report(out: Path, repo: RepoSnapshot, results: list[DrillResult], metadata_summary: dict | None = None, privacy_summary: dict | None = None) -> None:
    privacy_summary = validate_snapshot_projection(repo, privacy_summary)
    out = _safe_output_directory(out)
    _preflight_report_targets(out)
    payload = _safe_value({"schema_version": 1, "tool": {"name": "Maintainer-Zero", "version": __version__}, "rule_version": "0.2", "repository": repo.to_dict(), "results": [r.to_dict() for r in results]})
    if privacy_summary is not None:
        payload["privacy"] = _safe_value(privacy_summary)
    if metadata_summary is not None:
        payload["github_metadata"] = _safe_value(metadata_summary)
        payload["metadata_evidence"] = _metadata_evidence(metadata_summary)
    markdown = render_markdown(repo, results, metadata_summary, privacy_summary)
    body = html.escape(markdown).replace("\n", "<br>")
    _atomic_write_report_set(
        out,
        {
            "continuity.json": json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            "report.md": markdown,
            "report.html": f"<!doctype html><meta charset='utf-8'><title>Continuity Report</title><style>body{{font:16px system-ui;max-width:1000px;margin:40px auto;line-height:1.5}}</style><pre>{body}</pre>",
        },
    )
