from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from collections import Counter
from pathlib import Path

from .models import RepoSnapshot

MAX_REPOSITORY_FILE_BYTES = 1_048_576


def _is_link_like(info: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & reparse_flag)


def _safe_existing_directory(path: str | Path, label: str) -> Path:
    """Return an existing directory without following linked components."""
    target = Path(os.path.abspath(path))
    current = Path(target.anchor) if target.anchor else Path()
    parts = target.parts[1:] if target.anchor else target.parts
    for part in parts:
        current /= part
        try:
            info = current.lstat()
        except OSError as exc:
            raise ValueError(f"{label} is unavailable") from exc
        if _is_link_like(info):
            raise ValueError(f"{label} may not be a symlink or reparse point: {current}")
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"{label} is not a directory: {current}")
    return target


def _same_directory_stat(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        (getattr(left, "st_dev", -1), getattr(left, "st_ino", -1))
        == (getattr(right, "st_dev", -1), getattr(right, "st_ino", -1))
        and left.st_mode == right.st_mode
        and left.st_size == right.st_size
        and left.st_mtime_ns == right.st_mtime_ns
    )


def _reject_duplicate_object_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key: {key}")
        result[key] = value
    return result


def _reject_nonstandard_number(value: str) -> None:
    raise ValueError(f"non-standard JSON number: {value}")


def _safe_repo_path(root: Path, relative: str) -> Path | None:
    """Resolve a repository-relative path without following linked components.

    ``Path.resolve`` alone is only a containment check: it can still accept a
    symlinked parent that resolves back inside the checkout.  Walk each
    component with ``lstat`` so declarations are never silently read through
    an internal symlink/junction either.  The final component may be absent
    because callers use this helper for optional files.
    """
    candidate = root / relative
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    current = root
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or any(part == ".." for part in parts):
        return None
    for index, part in enumerate(parts):
        if part in ("", "."):
            continue
        current /= part
        # Leave the final component to the bounded descriptor reader.  That
        # keeps its initial ``lstat`` as the first observation of the file,
        # while parent components are still checked before path resolution.
        if index == len(parts) - 1:
            return candidate
        try:
            info = current.lstat()
        except FileNotFoundError:
            # Missing final files are valid optional inputs; a missing parent
            # means no descendant can be inspected safely.
            return candidate if index == len(parts) - 1 else None
        except (OSError, RuntimeError):
            return None
        if _is_link_like(info):
            return None
        if not stat.S_ISDIR(info.st_mode):
            return None
    return candidate


def _read_repo_file(root: Path, relative: str, *, max_bytes: int = MAX_REPOSITORY_FILE_BYTES) -> bytes | None:
    """Read one optional repository file through a stable, bounded descriptor."""
    candidate = _safe_repo_path(root, relative)
    if candidate is None:
        return None
    try:
        initial = candidate.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError(f"Cannot inspect repository file: {relative}") from exc
    if _is_link_like(initial) or not stat.S_ISREG(initial.st_mode):
        return None
    if initial.st_size > max_bytes:
        raise ValueError(f"Repository file exceeds size limit: {relative}")
    descriptor: int | None = None
    parent_descriptor: int | None = None
    try:
        # On platforms with ``dir_fd`` support, resolve every component from
        # an already-open directory descriptor.  This closes the parent
        # replacement window that a final-component ``O_NOFOLLOW`` alone
        # cannot cover (a swapped ``.github`` directory could otherwise
        # redirect a read outside the selected checkout).  Keep the bounded
        # path-based fallback for Windows, where dir_fd is unavailable; the
        # component lstat checks and final identity recheck still fail closed.
        parts = [part for part in Path(relative).parts if part not in ("", ".")]
        if os.open in getattr(os, "supports_dir_fd", set()):
            directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            parent_descriptor = os.open(root, directory_flags)
            for part in parts[:-1]:
                next_descriptor = os.open(part, directory_flags, dir_fd=parent_descriptor)
                os.close(parent_descriptor)
                parent_descriptor = next_descriptor
            descriptor = os.open(parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_descriptor)
        else:
            descriptor = os.open(candidate, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        if _is_link_like(opened) or not stat.S_ISREG(opened.st_mode):
            raise ValueError(f"Repository file is not a regular file: {relative}")
        identity = (getattr(initial, "st_dev", 0), getattr(initial, "st_ino", 0))
        opened_identity = (getattr(opened, "st_dev", 0), getattr(opened, "st_ino", 0))
        if opened_identity != identity:
            raise ValueError(f"Repository file changed before reading: {relative}")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            raw = handle.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError(f"Repository file exceeds size limit: {relative}")
        after = candidate.lstat()
        after_identity = (getattr(after, "st_dev", 0), getattr(after, "st_ino", 0))
        if (
            _is_link_like(after)
            or not stat.S_ISREG(after.st_mode)
            or after_identity != identity
            or after.st_size != initial.st_size
            or getattr(after, "st_mtime_ns", None) != getattr(initial, "st_mtime_ns", None)
        ):
            raise ValueError(f"Repository file changed during reading: {relative}")
        return raw
    except ValueError:
        raise
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Cannot read repository file: {relative}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)

def _run_git(path: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""

def _parse_codeowners(root: Path, relative: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    raw = _read_repo_file(root, relative)
    if raw is None:
        return result
    for line in raw.decode(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if parts and not parts[0].startswith("#") and len(parts) > 1:
            result[parts[0]] = parts[1:]
    return result

def _read_dependencies(path: Path) -> list[str]:
    found: set[str] = set()
    package = _safe_repo_path(path, "package.json")
    if package is not None:
        raw = _read_repo_file(path, "package.json")
    else:
        raw = None
    if raw is not None:
        try:
            data = json.loads(
                raw.decode(encoding="utf-8"),
                object_pairs_hook=_reject_duplicate_object_keys,
                parse_constant=_reject_nonstandard_number,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
            raise ValueError(f"Invalid dependency manifest: {package}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Invalid dependency manifest: {package}")
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            section = data.get(key, {})
            if not isinstance(section, dict) or any(not isinstance(name, str) or not name.strip() for name in section):
                raise ValueError(f"Invalid dependency manifest: {package}")
            found.update(section)
    for filename in ("requirements.txt", "requirements-dev.txt"):
        req = _safe_repo_path(path, filename)
        raw = _read_repo_file(path, filename) if req is not None else None
        if raw is not None:
            for line in raw.decode(encoding="utf-8", errors="replace").splitlines():
                match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9_.-]*)", line)
                if match and not line.lstrip().startswith("#"):
                    found.add(match.group(1).lower())
    return sorted(found)

def snapshot_repository(repo_path: str | Path) -> RepoSnapshot:
    path = _safe_existing_directory(repo_path, "repository")
    try:
        initial_path_stat = path.lstat()
    except OSError as exc:
        raise ValueError(f"Repository is unavailable: {path}") from exc
    # An empty Git response is not evidence of an empty repository.  Refuse
    # to analyze non-Git directories so callers cannot mistake missing git,
    # a broken worktree, or a command failure for a healthy zero-contributor
    # snapshot.
    try:
        probe = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise ValueError(f"Not a Git repository: {path}") from exc
    if probe.stdout.strip().lower() != "true":
        raise ValueError(f"Not a Git repository: {path}")
    raw = _run_git(path, "log", "--all", "--format=%an%x1f", "--name-only")
    contributors: Counter[str] = Counter()
    commits = 0
    for line in raw.splitlines():
        if line.endswith("\x1f") or ("\x1f" in line):
            name = line.split("\x1f", 1)[0].strip() or "unknown"
            contributors[name] += 1
            commits += 1
    codeowners = {}
    for relative in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
        candidate = _safe_repo_path(path, relative)
        if candidate is not None and _read_repo_file(path, relative) is not None:
            codeowners = _parse_codeowners(path, relative)
            break
    workflows_dir = _safe_repo_path(path, ".github/workflows")
    workflows = []
    if workflows_dir is not None:
        try:
            directory_info = workflows_dir.lstat()
        except FileNotFoundError:
            directory_info = None
        except OSError as exc:
            raise ValueError("Cannot inspect repository workflows directory") from exc
        if directory_info is not None and not _is_link_like(directory_info) and stat.S_ISDIR(directory_info.st_mode):
            try:
                candidates = list(workflows_dir.iterdir())
            except OSError as exc:
                raise ValueError("Cannot read repository workflows directory") from exc
            for candidate in candidates:
                if candidate.suffix.lower() not in {".yml", ".yaml"}:
                    continue
                relative = str(candidate.relative_to(path))
                if _read_repo_file(path, relative) is not None:
                    workflows.append(candidate.name)
            workflows.sort()
    release_files = []
    for relative in (".npmrc", ".pypirc", "release.config.js", ".github/workflows/release.yml", ".github/workflows/publish.yml"):
        if _read_repo_file(path, relative) is not None:
            release_files.append(relative)
    dependencies = _read_dependencies(path)
    try:
        final_path_stat = path.lstat()
    except OSError as exc:
        raise ValueError(f"Repository changed during analysis: {path}") from exc
    if not _same_directory_stat(initial_path_stat, final_path_stat) or _is_link_like(final_path_stat):
        raise ValueError(f"Repository changed during analysis: {path}")
    return RepoSnapshot(str(path), path.name, commits, dict(contributors), dependencies, workflows, codeowners, release_files)
