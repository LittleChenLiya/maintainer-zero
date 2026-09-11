"""Generate deterministic, local-only PR comment drafts."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

MAX_COMMENT_CHARS = 12_000
MAX_COMMENT_RESULTS = 500
MAX_INLINE_CHARS = 200


class PRCommentError(ValueError):
    """Raised when a comment draft is malformed or unsafe to publish."""

def _safe_inline(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PRCommentError(f"{label} must be a non-empty string")
    cleaned = "".join(char if char >= " " and char != "\x7f" else " " for char in value)
    cleaned = cleaned.replace("<", "&lt;").replace(">", "&gt;")
    cleaned = cleaned.replace(chr(96), chr(92) + chr(96))
    cleaned = " ".join(cleaned.split())
    if not cleaned or len(cleaned) > MAX_INLINE_CHARS:
        raise PRCommentError(f"{label} exceeds the inline text limit")
    return cleaned


def _repo(report: Mapping[str, Any]) -> tuple[str, str]:
    value = report.get("repository")
    if not isinstance(value, Mapping) or not isinstance(value.get("name"), str) or not isinstance(value.get("path"), str):
        raise PRCommentError("report repository name and path are required")
    return _safe_inline(value["name"], "repository name"), value["path"]


def _status(comparison: Mapping[str, Any] | None) -> str:
    if not comparison:
        return "current"
    status = comparison.get("status")
    return status if isinstance(status, str) and status else "changed"


def build_comment_draft(report: Mapping[str, Any], comparison: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Return a reviewable comment body and stable idempotency key; never sends it."""
    name, path = _repo(report)
    results = report.get("results")
    if not isinstance(results, list):
        raise PRCommentError("report results must be an array")
    if len(results) > MAX_COMMENT_RESULTS:
        raise PRCommentError("report results exceed the comment limit")
    lines = ["<!-- maintainer-zero:continuity-report -->", "## Maintainer-Zero continuity drill", "", f"Repository: `{name}`", f"Status: **{_status(comparison)}**", ""]
    for result in results:
        if not isinstance(result, Mapping) or not isinstance(result.get("scenario"), str):
            continue
        score = result.get("score")
        score_text = str(score) if isinstance(score, (int, float)) and not isinstance(score, bool) else "unknown"
        scenario = _safe_inline(result["scenario"], "scenario")
        lines.append(f"- `{scenario}`: **{score_text}/100**")
    lines.extend(["", "This comment is generated from a local report. Review unknown fields and findings before merging.", ""])
    body = "\n".join(lines)
    if len(body) > MAX_COMMENT_CHARS:
        raise PRCommentError("comment draft exceeds size limit")
    canonical = json.dumps({"repository": {"name": name, "path": path}, "body": body}, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {"body": body, "idempotency_key": hashlib.sha256(canonical).hexdigest()}


def publish_comment(
    draft: Mapping[str, str],
    *,
    enabled: bool = False,
    publisher: Any = None,
) -> str:
    """Publish only through an explicitly injected publisher; default is refusal."""
    if not enabled:
        raise PRCommentError("PR comment publishing is disabled; review the local draft instead")
    if publisher is None or not callable(publisher):
        raise PRCommentError("an explicit publisher is required for PR comment publishing")
    body, key = draft.get("body"), draft.get("idempotency_key")
    if not isinstance(body, str) or not isinstance(key, str) or not body or not key:
        raise PRCommentError("invalid comment draft")
    return str(publisher(body=body, idempotency_key=key))


__all__ = ["MAX_COMMENT_CHARS", "MAX_COMMENT_RESULTS", "PRCommentError", "build_comment_draft", "publish_comment"]
