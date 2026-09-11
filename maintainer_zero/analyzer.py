from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from .models import RepoSnapshot

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
    package = path / "package.json"
    if package.exists():
        try:
            data = json.loads(package.read_text(encoding="utf-8"))
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                found.update(str(k) for k in data.get(key, {}))
        except (OSError, json.JSONDecodeError):
            pass
    for filename in ("requirements.txt", "requirements-dev.txt"):
        req = path / filename
        if req.exists():
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
    for candidate in (path / ".github/CODEOWNERS", path / "CODEOWNERS", path / "docs/CODEOWNERS"):
        if candidate.exists():
            codeowners = _parse_codeowners(candidate)
            break
    workflows_dir = path / ".github/workflows"
    workflows = sorted(p.name for p in workflows_dir.glob("*.y*ml")) if workflows_dir.exists() else []
    release_files = [p for p in (".npmrc", ".pypirc", "release.config.js", ".github/workflows/release.yml", ".github/workflows/publish.yml") if (path / p).exists()]
    return RepoSnapshot(str(path), path.name, commits, dict(contributors), _read_dependencies(path), workflows, codeowners, release_files)
