"""Bounded local integrity manifests for generated artifacts."""
from __future__ import annotations

import hashlib, json, os, stat, tempfile
from pathlib import Path, PurePosixPath
from typing import Iterable
from . import __version__

SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 1_048_576
MAX_ARTIFACTS = 64
MAX_PATH_LENGTH = 256
MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
_CHUNK = 1024 * 1024

class ManifestError(ValueError):
    """Manifest validation failed closed."""

def _link(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))

def _directory(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    current = Path(path.anchor) if path.anchor else Path()
    parts = path.parts[1:] if path.anchor else path.parts
    for part in parts:
        current /= part
        try: info = current.lstat()
        except OSError as exc: raise ManifestError(f"cannot inspect manifest directory: {current}") from exc
        if _link(info) or not stat.S_ISDIR(info.st_mode):
            raise ManifestError(f"unsafe manifest directory: {current}")
    return path

def _relative(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_PATH_LENGTH:
        raise ManifestError("artifact path must be a bounded non-empty string")
    if any(ord(c) < 32 or ord(c) == 127 for c in value) or chr(92) in value:
        raise ManifestError("artifact path contains control characters or backslashes")
    p = PurePosixPath(value)
    if p.is_absolute() or value.startswith("/") or Path(value).drive or any(x in {"", ".", ".."} for x in p.parts) or p.as_posix() != value:
        raise ManifestError("artifact path must be normalized and relative")
    return value

def _artifact(root: Path, rel: str) -> Path:
    rel = _relative(rel); current = root
    parts = PurePosixPath(rel).parts
    for index, part in enumerate(parts):
        current /= part
        try: info = current.lstat()
        except OSError as exc: raise ManifestError(f"artifact is missing: {rel}") from exc
        if _link(info): raise ManifestError(f"artifact may not be a symlink or reparse point: {rel}")
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode): raise ManifestError(f"artifact parent is not a directory: {rel}")
    if not stat.S_ISREG(info.st_mode): raise ManifestError(f"artifact is not a regular file: {rel}")
    if info.st_size > MAX_ARTIFACT_BYTES: raise ManifestError(f"artifact exceeds size limit: {rel}")
    return current

def _entry(root: Path, item: str | Path):
    path = Path(item); path = path if path.is_absolute() else root / path
    try: rel = _relative(Path(os.path.relpath(path, root)).as_posix())
    except (ValueError, ManifestError): return None
    if rel == "artifact-manifest.json": return None
    target = _artifact(root, rel); digest = hashlib.sha256(); total = 0
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            total += len(chunk)
            if total > MAX_ARTIFACT_BYTES: raise ManifestError(f"artifact exceeds size limit: {rel}")
            digest.update(chunk)
    return {"path": rel, "size": total, "sha256": digest.hexdigest()}

def _write(path: Path, text: str):
    parent = _directory(path.parent)
    if os.path.lexists(path):
        info = path.lstat()
        if _link(info) or not stat.S_ISREG(info.st_mode): raise ManifestError("manifest target is unsafe")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=parent, prefix=".artifact-manifest.", suffix=".tmp", delete=False) as h:
            temporary = Path(h.name); h.write(text); h.flush(); os.fsync(h.fileno())
        os.replace(temporary, path); temporary = None
    except OSError as exc: raise ManifestError(f"cannot write manifest: {path}") from exc
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)

def write_manifest(output: str | Path, artifacts: Iterable[str | Path]) -> Path:
    root = _directory(Path(output)); entries = []; seen = set()
    for item in artifacts:
        entry = _entry(root, item)
        if entry is None: continue
        key = entry["path"].casefold()
        if key not in seen: seen.add(key); entries.append(entry)
    entries.sort(key=lambda x: x["path"])
    if not entries: raise ManifestError("manifest requires at least one artifact")
    if len(entries) > MAX_ARTIFACTS: raise ManifestError("manifest has too many artifacts")
    payload = {"schema_version": SCHEMA_VERSION, "tool": {"name": "Maintainer-Zero", "version": __version__}, "rule_version": "0.2", "artifacts": entries}
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if len(text.encode("utf-8")) > MAX_MANIFEST_BYTES: raise ManifestError("manifest exceeds size limit")
    target = root / "artifact-manifest.json"; _write(target, text); return target

def load_manifest(path: str | Path) -> dict:
    target = Path(path)
    try: info = target.lstat()
    except OSError as exc: raise ManifestError(f"cannot inspect manifest: {target}") from exc
    if _link(info) or not stat.S_ISREG(info.st_mode): raise ManifestError("manifest must be a regular file")
    if info.st_size > MAX_MANIFEST_BYTES: raise ManifestError("manifest exceeds size limit")
    try: payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ManifestError("invalid manifest JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "tool", "rule_version", "artifacts"}: raise ManifestError("manifest fields are invalid")
    if payload["schema_version"] != SCHEMA_VERSION: raise ManifestError("unsupported manifest schema version")
    tool = payload["tool"]
    if not isinstance(tool, dict) or set(tool) != {"name", "version"} or tool.get("name") != "Maintainer-Zero" or not isinstance(tool.get("version"), str): raise ManifestError("manifest tool metadata is invalid")
    if not isinstance(payload["rule_version"], str): raise ManifestError("manifest rule version is invalid")
    items = payload["artifacts"]
    if not isinstance(items, list) or not items or len(items) > MAX_ARTIFACTS: raise ManifestError("manifest artifacts are invalid")
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}: raise ManifestError("invalid artifact entry")
        rel = _relative(item["path"]); key = rel.casefold()
        if key in seen: raise ManifestError("duplicate artifact path")
        seen.add(key); size = item["size"]
        if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= MAX_ARTIFACT_BYTES: raise ManifestError("invalid artifact size")
        digest = item["sha256"]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest): raise ManifestError("invalid artifact SHA-256")
    return payload

def verify_manifest(path: str | Path) -> dict:
    manifest = Path(path); payload = load_manifest(manifest); root = _directory(manifest.parent); checked = []
    for item in payload["artifacts"]:
        rel = item["path"]; target = _artifact(root, rel); before = target.lstat(); digest = hashlib.sha256(); total = 0
        try:
            with target.open("rb") as handle:
                opened = os.fstat(handle.fileno())
                if _link(opened) or not stat.S_ISREG(opened.st_mode): raise ManifestError(f"artifact is not regular: {rel}")
                for chunk in iter(lambda: handle.read(_CHUNK), b""):
                    total += len(chunk); digest.update(chunk)
                    if total > MAX_ARTIFACT_BYTES: raise ManifestError(f"artifact exceeds size limit: {rel}")
        except OSError as exc: raise ManifestError(f"cannot read artifact: {rel}") from exc
        after = target.lstat()
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns: raise ManifestError(f"artifact changed during verification: {rel}")
        if total != item["size"]: raise ManifestError(f"artifact size mismatch: {rel}")
        if digest.hexdigest() != item["sha256"]: raise ManifestError(f"artifact hash mismatch: {rel}")
        checked.append(rel)
    return {"verified": len(checked), "artifacts": checked, "manifest": str(manifest)}
