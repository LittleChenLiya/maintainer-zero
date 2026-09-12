from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from .models import RepoSnapshot


def _safe_repo_path(root: Path, relative: str) -> Path | None:
    """Resolve a repository-relative path without following it outside root."""
    candidate = root / relative
    try:
        candidate.resolve().relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate

def _run_git(path: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""

def _parse_codeowners(path: Path) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if parts and not parts[0].startswith("#") and len(parts) > 1:
            result[parts[0]] = parts[1:]
    return result

def _read_dependencies(path: Path) -> list[str]:
    found: set[str] = set()
    package = _safe_repo_path(path, "package.json")
    if package is not None and package.is_file():
        try:
            data = json.loads(package.read_text(encoding="utf-8"))
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                found.update(str(k) for k in data.get(key, {}))
        except (OSError, json.JSONDecodeError):
            pass
    for filename in ("requirements.txt", "requirements-dev.txt"):
        req = _safe_repo_path(path, filename)
        if req is not None and req.is_file():
            for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
                match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9_.-]*)", line)
                if match and not line.lstrip().startswith("#"):
                    found.add(match.group(1).lower())
    return sorted(found)

def snapshot_repository(repo_path: str | Path) -> RepoSnapshot:
    path = Path(repo_path).resolve()
    if not path.is_dir():
        raise ValueError(f"Repository does not exist: {path}")
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
        if candidate is not None and candidate.is_file():
            codeowners = _parse_codeowners(candidate)
            break
    workflows_dir = _safe_repo_path(path, ".github/workflows")
    workflows = sorted(p.name for p in workflows_dir.glob("*.y*ml") if _safe_repo_path(path, str(p.relative_to(path))) is not None) if workflows_dir is not None and workflows_dir.is_dir() else []
    release_files = [relative for relative in (".npmrc", ".pypirc", "release.config.js", ".github/workflows/release.yml", ".github/workflows/publish.yml") if (candidate := _safe_repo_path(path, relative)) is not None and candidate.is_file()]
    return RepoSnapshot(str(path), path.name, commits, dict(contributors), _read_dependencies(path), workflows, codeowners, release_files)
