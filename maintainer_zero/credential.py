"""Offline-verifiable integrity credentials for a drill output.

This is a content-integrity envelope, not a digital signature: it proves that
referenced files still match their recorded hashes, not who created them.
"""
from __future__ import annotations
import hashlib, json, os, stat, tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from . import __version__
from .manifest import ManifestError, verify_manifest
SCHEMA_VERSION = 1
MAX_CREDENTIAL_BYTES = 256 * 1024
MAX_BOUND_FILE_BYTES = 8 * 1024 * 1024
_BOUNDARY = b"\n--maintainer-zero-integrity-boundary--\n"
class CredentialError(ValueError):
    """Credential validation failed closed."""
def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result: raise CredentialError(f"credential contains duplicate object key: {key}")
        result[key] = value
    return result
def _constant(value: str) -> None: raise CredentialError(f"credential contains non-standard JSON number: {value}")
def _link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
def _rel(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 256: raise CredentialError("credential path must be a bounded relative string")
    path = PurePosixPath(value); windows = PureWindowsPath(value)
    if path.is_absolute() or windows.drive or windows.root or "\\" in value or any(ord(char) < 32 or ord(char) == 127 for char in value) or path.as_posix() != value or any(part in {"", ".", ".."} for part in path.parts): raise CredentialError("credential path must be normalized and relative")
    return value
def _safe_directory(path: Path) -> Path:
    target = Path(os.path.abspath(path)); current = Path(target.anchor) if target.anchor else Path(); parts = target.parts[1:] if target.anchor else target.parts
    for part in parts:
        current /= part
        try: info = current.lstat()
        except OSError as exc: raise CredentialError(f"credential directory is missing: {current}") from exc
        if _link(info) or not stat.S_ISDIR(info.st_mode): raise CredentialError("credential parent must be a real directory")
    return target
def _safe_file(path: Path, label: str) -> tuple[Path, os.stat_result]:
    target = Path(os.path.abspath(path)); _safe_directory(target.parent)
    try: info = target.lstat()
    except OSError as exc: raise CredentialError(f"{label} is missing") from exc
    if _link(info) or not stat.S_ISREG(info.st_mode): raise CredentialError(f"{label} must be a regular file")
    return target, info
def _read(root: Path, relative: str) -> bytes:
    relative = _rel(relative); target, info = _safe_file(root / relative, "credential-bound file")
    if info.st_size > MAX_BOUND_FILE_BYTES: raise CredentialError(f"credential-bound file exceeds size limit: {relative}")
    try:
        with target.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if _link(opened) or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino): raise CredentialError(f"credential-bound file changed before reading: {relative}")
            raw = handle.read(MAX_BOUND_FILE_BYTES + 1)
        after = target.lstat()
    except CredentialError: raise
    except OSError as exc: raise CredentialError(f"cannot read credential-bound file: {relative}") from exc
    if len(raw) > MAX_BOUND_FILE_BYTES or (after.st_dev, after.st_ino) != (info.st_dev, info.st_ino) or after.st_size != info.st_size or getattr(after, "st_mtime_ns", None) != getattr(info, "st_mtime_ns", None): raise CredentialError(f"credential-bound file changed during reading: {relative}")
    return raw
def _sha(raw: bytes) -> str: return hashlib.sha256(raw).hexdigest()
def _content_digest(report: bytes, manifest: bytes) -> str: return _sha(report + _BOUNDARY + manifest)
def _write(path: Path, text: str) -> None:
    _safe_directory(path.parent)
    if os.path.lexists(path):
        info = path.lstat()
        if _link(info) or not stat.S_ISREG(info.st_mode): raise CredentialError("credential output must be a regular file")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, prefix=".credential.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name); handle.write(text); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path); temporary = None
    except OSError as exc: raise CredentialError(f"cannot write credential: {path}") from exc
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)
def _payload(report_name: str, report: bytes, manifest_name: str, manifest: bytes) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "credential_type": "maintainer-zero.integrity", "tool": {"name": "Maintainer-Zero", "version": __version__}, "rule_version": "0.2", "claims": ["offline-content-integrity-only", "not-a-digital-signature", "does-not-prove-source-or-authority"], "report": {"path": report_name, "size": len(report), "sha256": _sha(report)}, "manifest": {"path": manifest_name, "size": len(manifest), "sha256": _sha(manifest)}, "content_digest": {"algorithm": "sha256", "value": _content_digest(report, manifest)}}
def create_credential(report: str | Path, manifest: str | Path, output: str | Path | None = None) -> Path:
    report_path, manifest_path = Path(os.path.abspath(report)), Path(os.path.abspath(manifest))
    if report_path.parent != manifest_path.parent: raise CredentialError("report and manifest must share a directory")
    root = _safe_directory(report_path.parent); report_raw, manifest_raw = _read(root, report_path.name), _read(root, manifest_path.name)
    try: verify_manifest(manifest_path)
    except ManifestError as exc: raise CredentialError(f"manifest is not verifiable: {exc}") from exc
    target = Path(os.path.abspath(output)) if output is not None else root / "continuity-credential.json"
    if target.parent != root: raise CredentialError("credential output must share a directory with report and manifest")
    if target in {report_path, manifest_path}: raise CredentialError("credential output must not replace report or manifest")
    text = json.dumps(_payload(report_path.name, report_raw, manifest_path.name, manifest_raw), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if len(text.encode("utf-8")) > MAX_CREDENTIAL_BYTES: raise CredentialError("credential exceeds size limit")
    _write(target, text); return target
def load_credential(path: str | Path) -> dict[str, Any]:
    target, info = _safe_file(Path(path), "credential")
    try:
        if info.st_size > MAX_CREDENTIAL_BYTES: raise CredentialError("credential exceeds size limit")
        with target.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if _link(opened) or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino): raise CredentialError("credential changed before reading")
            raw = handle.read(MAX_CREDENTIAL_BYTES + 1)
        after = target.lstat()
        if len(raw) > MAX_CREDENTIAL_BYTES or (after.st_dev, after.st_ino) != (info.st_dev, info.st_ino) or after.st_size != info.st_size or getattr(after, "st_mtime_ns", None) != getattr(info, "st_mtime_ns", None): raise CredentialError("credential changed during reading")
    except CredentialError: raise
    except OSError as exc: raise CredentialError("cannot read credential") from exc
    try: payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicates, parse_constant=_constant)
    except RecursionError as exc: raise CredentialError("credential JSON is too deeply nested") from exc
    except CredentialError: raise
    except (UnicodeError, json.JSONDecodeError) as exc: raise CredentialError("invalid credential JSON") from exc
    required = {"schema_version", "credential_type", "tool", "rule_version", "claims", "report", "manifest", "content_digest"}
    if not isinstance(payload, dict) or set(payload) != required or payload["schema_version"] != SCHEMA_VERSION or payload["credential_type"] != "maintainer-zero.integrity": raise CredentialError("credential fields or schema are invalid")
    tool = payload["tool"]
    if not isinstance(tool, dict) or set(tool) != {"name", "version"} or tool.get("name") != "Maintainer-Zero" or not isinstance(tool.get("version"), str) or not tool["version"].strip(): raise CredentialError("credential tool metadata is invalid")
    if payload["rule_version"] != "0.2" or payload["claims"] != ["offline-content-integrity-only", "not-a-digital-signature", "does-not-prove-source-or-authority"]: raise CredentialError("credential claims are invalid")
    for name in ("report", "manifest"):
        item = payload[name]
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}: raise CredentialError(f"credential {name} reference is invalid")
        _rel(item["path"])
        if isinstance(item["size"], bool) or not isinstance(item["size"], int) or not 0 <= item["size"] <= MAX_BOUND_FILE_BYTES: raise CredentialError(f"credential {name} size is invalid")
        if not isinstance(item["sha256"], str) or len(item["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in item["sha256"]): raise CredentialError(f"credential {name} hash is invalid")
    digest = payload["content_digest"]
    if not isinstance(digest, dict) or set(digest) != {"algorithm", "value"} or digest.get("algorithm") != "sha256" or not isinstance(digest.get("value"), str) or len(digest["value"]) != 64 or any(c not in "0123456789abcdef" for c in digest["value"]): raise CredentialError("credential content digest is invalid")
    return payload
def verify_credential(path: str | Path) -> dict[str, Any]:
    credential = Path(os.path.abspath(path)); payload = load_credential(credential); root = credential.parent
    report_raw, manifest_raw = _read(root, payload["report"]["path"]), _read(root, payload["manifest"]["path"])
    for name, raw in (("report", report_raw), ("manifest", manifest_raw)):
        item = payload[name]
        if len(raw) != item["size"] or _sha(raw) != item["sha256"]: raise CredentialError(f"credential {name} hash mismatch")
    try: verify_manifest(root / payload["manifest"]["path"])
    except ManifestError as exc: raise CredentialError(f"manifest verification failed: {exc}") from exc
    actual = _content_digest(report_raw, manifest_raw)
    if actual != payload["content_digest"]["value"]: raise CredentialError("credential content digest mismatch")
    return {"verified": True, "report": payload["report"]["path"], "manifest": payload["manifest"]["path"], "content_digest": actual}
__all__ = ["CredentialError", "create_credential", "load_credential", "verify_credential"]
