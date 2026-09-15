"""Local, same-repository continuity report history and trend summaries.

History is intentionally a small JSON document rather than a database.  It stores
scores and finding counts, never raw repository records, and refuses to mix
reports whose repository identity does not match the history owner.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from . import __version__

HISTORY_SCHEMA_VERSION = 1
MAX_HISTORY_ENTRIES = 1_000
MAX_HISTORY_STRING = 512
MAX_HISTORY_BYTES = 10_000_000
_HISTORY_KEYS = frozenset({"schema_version", "repository", "repository_id", "rule_version", "tool_version", "entries"})


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject ambiguous JSON objects instead of silently keeping the last key."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HistoryError(f"history contains duplicate object key: {key}")
        result[key] = value
    return result


def _reject_nonstandard_number(value: str) -> None:
    """Reject NaN/Infinity, which are outside the JSON data contract."""
    raise HistoryError(f"history contains non-standard JSON number: {value}")


class HistoryError(ValueError):
    """Raised when a history file is malformed or belongs to another repository."""


def _is_link_like(info: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & reparse_flag)


def _prepare_history_path(path: str | Path, *, create_parents: bool) -> Path:
    target = Path(path)
    if not target.is_absolute():
        target = Path.cwd() / target
    current = Path(target.anchor) if target.anchor else Path()
    parts = target.parts[1:] if target.anchor else target.parts
    for part in parts[:-1]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if not create_parents:
                break
            current.mkdir()
            info = current.lstat()
        if _is_link_like(info):
            raise HistoryError("history path may not contain a symlink or reparse point")
        if not stat.S_ISDIR(info.st_mode):
            raise HistoryError("history parent must be a directory")
    try:
        info = target.lstat()
    except FileNotFoundError:
        return target
    if _is_link_like(info) or not stat.S_ISREG(info.st_mode):
        raise HistoryError("history file must be a regular file")
    return target


def _read_history(path: Path) -> dict[str, Any]:
    try:
        info = path.lstat()
        if _is_link_like(info) or not stat.S_ISREG(info.st_mode):
            raise HistoryError("history file must be a regular file")
        if info.st_size > MAX_HISTORY_BYTES:
            raise HistoryError(f"history file exceeds {MAX_HISTORY_BYTES} bytes")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        if _is_link_like(info) or not stat.S_ISREG(info.st_mode) or not stat.S_ISREG(opened.st_mode):
            os.close(descriptor)
            raise HistoryError("history file must be a regular file")
        if (getattr(info, "st_dev", 0), getattr(info, "st_ino", 0)) != (getattr(opened, "st_dev", 0), getattr(opened, "st_ino", 0)):
            os.close(descriptor)
            raise HistoryError("history file changed during open")
        with os.fdopen(descriptor, "rb") as handle:
            raw = handle.read(MAX_HISTORY_BYTES + 1)
        if len(raw) > MAX_HISTORY_BYTES:
            raise HistoryError(f"history file exceeds {MAX_HISTORY_BYTES} bytes")
        try:
            after = path.lstat()
        except OSError as exc:
            raise HistoryError("history file changed during reading") from exc
        if (
            _is_link_like(after)
            or not stat.S_ISREG(after.st_mode)
            or (getattr(info, "st_dev", 0), getattr(info, "st_ino", 0))
            != (getattr(after, "st_dev", 0), getattr(after, "st_ino", 0))
            or after.st_size != info.st_size
            or getattr(after, "st_mtime_ns", None) != getattr(info, "st_mtime_ns", None)
        ):
            raise HistoryError("history file changed during reading")
        payload = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_number,
        )
    except HistoryError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise HistoryError(f"Invalid continuity history: {path}") from exc
    if not isinstance(payload, dict):
        raise HistoryError("continuity history must be a JSON object")
    _validate_history(payload)
    return payload


def _repository(report: Mapping[str, Any]) -> dict[str, str]:
    repository = report.get("repository")
    if not isinstance(repository, Mapping):
        raise HistoryError("continuity report repository must be an object")
    name, path = repository.get("name"), repository.get("path")
    if not isinstance(name, str) or not name.strip() or not isinstance(path, str) or not path.strip():
        raise HistoryError("continuity report repository name and path are required")
    if len(name) > MAX_HISTORY_STRING or len(path) > MAX_HISTORY_STRING:
        raise HistoryError("continuity report repository identity is too long")
    return {"name": name, "path": path}


def _identity(repository: Mapping[str, str]) -> str:
    value = f"{repository['name']}\0{repository['path']}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:16]


def _score(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    score = round(float(value))
    return score if 0 <= score <= 100 else None


def _rule_version(value: Any, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        raise HistoryError("rule_version must be a non-empty string")
    return value


def _tool_version(value: Any, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        raise HistoryError("tool_version must be a non-empty string")
    return value


def _recorded_at(value: Any) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise HistoryError("history recorded_at must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HistoryError("history recorded_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise HistoryError("history recorded_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def _bounded_int(value: Any, *, minimum: int = 0, maximum: int | None = None) -> bool:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        return False
    return maximum is None or value <= maximum


def _validate_entry(entry: Mapping[str, Any], rule_version: str | None, tool_version: str | None) -> None:
    required = {"recorded_at", "rule_version", "overall_score", "scenarios", "finding_counts", "high_risk_findings"}
    allowed = required | {"tool_version"}
    if set(entry) not in (required, allowed):
        raise HistoryError("history entries are malformed")
    _recorded_at(entry["recorded_at"])
    entry_rule = _rule_version(entry["rule_version"], required=True)
    if rule_version is not None and entry_rule != rule_version:
        raise HistoryError("history entries use different rule versions")
    entry_tool = _tool_version(entry.get("tool_version"))
    if tool_version is not None and entry_tool is not None and entry_tool != tool_version:
        raise HistoryError("history entries use different tool versions")
    score = entry["overall_score"]
    if score is not None and not _bounded_int(score, maximum=100):
        raise HistoryError("history overall_score must be an integer from 0 to 100 or null")
    for key in ("scenarios", "finding_counts"):
        values = entry[key]
        if not isinstance(values, dict) or len(values) > 128:
            raise HistoryError(f"history {key} must be a bounded object")
        for name, value in values.items():
            if not isinstance(name, str) or not name.strip() or len(name) > 128:
                raise HistoryError(f"history {key} contains an invalid scenario name")
            if key == "scenarios":
                if value is not None and not _bounded_int(value, maximum=100):
                    raise HistoryError("history scenario scores must be integers from 0 to 100 or null")
            elif not _bounded_int(value):
                raise HistoryError("history finding counts must be non-negative integers")
    if not _bounded_int(entry["high_risk_findings"]):
        raise HistoryError("history high_risk_findings must be a non-negative integer")


def summarize_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Extract trend-safe aggregates from a full continuity report."""
    repository = _repository(report)
    rule_version = _rule_version(report.get("rule_version"), required=True)
    tool = report.get("tool")
    tool_version = None
    if tool is not None:
        if not isinstance(tool, Mapping) or tool.get("name") != "Maintainer-Zero":
            raise HistoryError("continuity report tool metadata is invalid")
        tool_version = _tool_version(tool.get("version"), required=True)
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
        raw_score = result.get("score")
        score = _score(raw_score)
        if raw_score is not None and score is None:
            raise HistoryError("continuity report scores must be between 0 and 100")
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
        "rule_version": rule_version,
        "tool_version": tool_version,
        "overall_score": round(sum(scores) / len(scores)) if scores else None,
        "scenarios": scenarios,
        "finding_counts": finding_counts,
        "high_risk_findings": high_risk,
    }


def _validate_history(payload: Mapping[str, Any]) -> None:
    if set(payload) - _HISTORY_KEYS:
        raise HistoryError("continuity history contains unsupported fields")
    if payload.get("schema_version") != HISTORY_SCHEMA_VERSION:
        raise HistoryError("unsupported history schema_version")
    repository = payload.get("repository")
    if not isinstance(repository, Mapping) or not isinstance(repository.get("name"), str) or not isinstance(repository.get("path"), str):
        raise HistoryError("history repository must include name and path")
    expected_id = _identity({"name": repository["name"], "path": repository["path"]})
    repository_id = payload.get("repository_id")
    if repository_id is not None and repository_id != expected_id:
        raise HistoryError("history repository_id does not match repository")
    rule_version = _rule_version(payload.get("rule_version"))
    tool_version = _tool_version(payload.get("tool_version"))
    entries = payload.get("entries")
    if not isinstance(entries, list) or len(entries) > MAX_HISTORY_ENTRIES:
        raise HistoryError(f"history entries must be an array of at most {MAX_HISTORY_ENTRIES} items")
    # v1 histories written before the root-level rule_version field are still
    # readable; derive the rule from their first compact entry and let callers
    # rewrite the root field on the next append.
    if entries and rule_version is None:
        first_entry = entries[0]
        if isinstance(first_entry, Mapping):
            rule_version = _rule_version(first_entry.get("rule_version"), required=True)
    previous_at: datetime | None = None
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise HistoryError("history entries are malformed")
        _validate_entry(entry, rule_version, tool_version)
        recorded_at = _recorded_at(entry["recorded_at"])
        if previous_at is not None and recorded_at < previous_at:
            raise HistoryError("history entries must be ordered by recorded_at")
        previous_at = recorded_at


def load_history(path: str | Path) -> dict[str, Any]:
    history_path = _prepare_history_path(path, create_parents=False)
    return _read_history(history_path)


def append_history(path: str | Path, report: Mapping[str, Any], *, recorded_at: str | None = None) -> dict[str, Any]:
    """Append a compact report aggregate and return the trend summary."""
    path = _prepare_history_path(path, create_parents=True)
    summary = summarize_report(report)
    # Re-check the target without following a symlink.  ``Path.exists()``
    # follows links and can also turn a target that disappears during the
    # preflight into a misleading "new history" branch.  A missing target
    # is only treated as new when the same lstat observation says it is absent;
    # any replacement between this check and ``load_history`` fails closed via
    # its descriptor identity checks.
    try:
        target_info = path.lstat()
    except FileNotFoundError:
        target_info = None
    except OSError as exc:
        raise HistoryError(f"could not inspect history path: {path}") from exc
    if target_info is not None:
        if _is_link_like(target_info) or not stat.S_ISREG(target_info.st_mode):
            raise HistoryError("history file must be a regular file")
        payload = load_history(path)
        owner = payload["repository"]
        if owner.get("name") != summary["repository"]["name"] or owner.get("path") != summary["repository"]["path"]:
            raise HistoryError("history belongs to a different repository")
    else:
        payload = {"schema_version": HISTORY_SCHEMA_VERSION, "repository": summary["repository"], "repository_id": summary["repository_id"], "rule_version": summary["rule_version"], "tool_version": summary["tool_version"], "entries": []}
    entries = payload["entries"]
    if len(entries) >= MAX_HISTORY_ENTRIES:
        raise HistoryError(f"history entries limit reached ({MAX_HISTORY_ENTRIES})")
    history_rule = payload.get("rule_version") or summary["rule_version"]
    if history_rule != summary["rule_version"]:
        raise HistoryError("history belongs to a different rule version")
    history_tool = _tool_version(payload.get("tool_version"))
    if history_tool is not None and summary["tool_version"] is not None and history_tool != summary["tool_version"]:
        raise HistoryError("history belongs to a different tool version")
    payload["rule_version"] = history_rule
    payload["tool_version"] = history_tool or summary["tool_version"]
    payload["repository_id"] = payload.get("repository_id") or summary["repository_id"]
    timestamp = recorded_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if entries and _recorded_at(timestamp) < _recorded_at(entries[-1]["recorded_at"]):
        raise HistoryError("recorded_at must not move backwards")
    entry = {
        "recorded_at": timestamp,
        **{key: summary[key] for key in ("rule_version", "overall_score", "scenarios", "finding_counts", "high_risk_findings")},
    }
    if summary["tool_version"] is not None:
        entry["tool_version"] = summary["tool_version"]
    entries.append(entry)
    encoded = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise HistoryError(f"could not atomically write history: {path}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
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
    def map_delta(left: Mapping[str, Any] | None, right: Mapping[str, Any] | None) -> dict[str, int]:
        result: dict[str, int] = {}
        if left and right:
            names = set((left.get("scenarios") or {})) | set((right.get("scenarios") or {}))
            for name in sorted(names):
                old, new = (left.get("scenarios") or {}).get(name), (right.get("scenarios") or {}).get(name)
                if isinstance(old, int) and isinstance(new, int):
                    result[name] = new - old
        return result
    scenario_delta_previous = map_delta(previous, latest)
    def count_delta(left: Mapping[str, Any] | None, right: Mapping[str, Any] | None) -> dict[str, int]:
        result: dict[str, int] = {}
        if left and right:
            names = set((left.get("finding_counts") or {})) | set((right.get("finding_counts") or {}))
            for name in sorted(names):
                old, new = (left.get("finding_counts") or {}).get(name), (right.get("finding_counts") or {}).get(name)
                if isinstance(old, int) and isinstance(new, int):
                    result[name] = new - old
        return result
    finding_delta = count_delta(first, latest)
    finding_delta_previous = count_delta(previous, latest)
    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "repository": payload["repository"],
        "repository_id": payload.get("repository_id") or _identity(payload["repository"]),
        "rule_version": payload.get("rule_version") or (latest or {}).get("rule_version"),
        "tool_version": payload.get("tool_version") or (latest or {}).get("tool_version"),
        "runs": len(entries),
        "latest": latest,
        "delta_since_previous": delta(previous, latest, "overall_score"),
        "delta_since_first": delta(first, latest, "overall_score"),
        "scenario_delta_since_first": scenario_delta,
        "scenario_delta_since_previous": scenario_delta_previous,
        "finding_count_delta_since_first": finding_delta,
        "finding_count_delta_since_previous": finding_delta_previous,
        "high_risk_delta_since_first": delta(first, latest, "high_risk_findings"),
        "high_risk_delta_since_previous": delta(previous, latest, "high_risk_findings"),
    }


def _markdown_value(value: Any) -> str:
    """Render a bounded trend value without Markdown structure injection."""
    if value is None:
        return "unknown"
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = "".join(char if char.isprintable() or char == "\t" else " " for char in text).strip()
    if not text:
        return "unknown"
    # Values are inserted into list items and table cells. Escape punctuation
    # that could create links, emphasis, code spans, HTML, or table columns.
    punctuation = chr(96) + "*_[\\]()<>{}#+!~|"
    return "".join("\\" + char if char in punctuation else char for char in text) or "unknown"


def render_trend_markdown(summary: Mapping[str, Any]) -> str:
    """Render a path-free, human-reviewable trend summary."""
    repository = summary.get("repository") if isinstance(summary, Mapping) else None
    repository_name = repository.get("name") if isinstance(repository, Mapping) else None
    latest = summary.get("latest")
    latest_score = latest.get("overall_score") if isinstance(latest, Mapping) else None
    lines = [
        "# Continuity trend summary", "",
        f"- Repository: {_markdown_value(repository_name)}",
        f"- Rule version: {_markdown_value(summary.get('rule_version'))}",
        f"- Tool version: {_markdown_value(summary.get('tool_version'))}",
        f"- Runs: {_markdown_value(summary.get('runs'))}",
        f"- Latest overall score: {_markdown_value(latest_score)}",
        f"- Change since previous: {_markdown_value(summary.get('delta_since_previous'))}",
        f"- Change since first: {_markdown_value(summary.get('delta_since_first'))}", "",
        "> This is a local, same-repository aggregate. unknown means unavailable; it is not a zero-risk or recovery claim.", "",
    ]
    previous = summary.get("scenario_delta_since_previous")
    first = summary.get("scenario_delta_since_first")
    previous = previous if isinstance(previous, Mapping) else {}
    first = first if isinstance(first, Mapping) else {}
    names = sorted(set(previous) | set(first), key=str)
    lines.extend(["## Scenario score changes", "", "| Scenario | Since previous | Since first |", "| --- | ---: | ---: |"])
    lines.extend(f"| {_markdown_value(name)} | {_markdown_value(previous.get(name))} | {_markdown_value(first.get(name))} |" for name in names)
    if not names:
        lines.append("| No comparable scenarios | unknown | unknown |")
    lines.extend(["", "## Finding and high-risk changes", "", f"- Finding count change since previous: {_markdown_value(summary.get('finding_count_delta_since_previous'))}", f"- Finding count change since first: {_markdown_value(summary.get('finding_count_delta_since_first'))}", f"- High-risk change since previous: {_markdown_value(summary.get('high_risk_delta_since_previous'))}", f"- High-risk change since first: {_markdown_value(summary.get('high_risk_delta_since_first'))}", ""])
    return "\n".join(lines)


__all__ = ["HISTORY_SCHEMA_VERSION", "HistoryError", "append_history", "load_history", "render_trend_markdown", "summarize_report", "trend_summary"]
