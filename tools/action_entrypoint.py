"""Environment-to-argv adapter for the composite GitHub Action.

Inputs arrive through the action environment rather than shell interpolation.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

from maintainer_zero.cli import main

_CONTROL_CHARS = frozenset(chr(code) for code in range(32)) | {chr(127)}
_PATH_INPUTS = ("MZ_INPUT_PATH", "MZ_INPUT_OUTPUT", "MZ_INPUT_BASELINE", "MZ_INPUT_METADATA", "MZ_INPUT_HISTORY", "MZ_INPUT_FALLBACK_PLAN")


def _is_link_like(info: os.stat_result) -> bool:
    """Treat Windows junctions/reparse points as links as well as POSIX symlinks."""
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & reparse_flag)


def _absolute_path(value: str | Path) -> Path:
    """Make a path absolute while preserving ``..`` for component checks."""
    target = Path(os.fspath(value))
    return target if target.is_absolute() else Path.cwd() / target


def _validate_path_components(
    value: str | Path,
    label: str,
    *,
    require_existing: bool = False,
    require_directory: bool = False,
) -> Path:
    """Reject linked path components before any Action path is consumed."""
    target = _absolute_path(value)
    current = Path(target.anchor) if target.anchor else Path()
    parts = target.parts[1:] if target.anchor else target.parts
    missing = False
    last_info: os.stat_result | None = None
    if not parts and target.anchor:
        try:
            last_info = target.lstat()
        except OSError as exc:
            raise ValueError(f"{label} path could not be inspected") from exc
        if _is_link_like(last_info) or not stat.S_ISDIR(last_info.st_mode):
            raise ValueError(f"{label} must be an existing directory")
    for index, part in enumerate(parts):
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            missing = True
            if require_existing:
                raise ValueError(f"{label} does not exist")
            break
        except OSError as exc:
            raise ValueError(f"{label} path could not be inspected") from exc
        if _is_link_like(info):
            scope = "parent path" if index < len(parts) - 1 else "path"
            raise ValueError(f"{label} {scope} may not contain a symbolic link or reparse point")
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"{label} parent path is not a directory")
        last_info = info
    if require_directory and (missing or last_info is None or not stat.S_ISDIR(last_info.st_mode)):
        raise ValueError(f"{label} must be an existing directory")
    return target


def _validate_environment(env: dict[str, str]) -> None:
    """Reject control characters and workspace escapes in Action inputs."""
    for key in _PATH_INPUTS:
        if any(char in _CONTROL_CHARS for char in env.get(key, "")):
            raise ValueError(f"{key} contains control characters")
    workspace = env.get("MZ_INPUT_WORKSPACE", "").strip()
    if any(char in _CONTROL_CHARS for char in workspace):
        raise ValueError("MZ_INPUT_WORKSPACE contains control characters")
    workspace_path = None
    if workspace:
        workspace_path = _validate_path_components(
            workspace, "MZ_INPUT_WORKSPACE", require_existing=True, require_directory=True
        )
        workspace_path = Path(os.path.normpath(os.fspath(workspace_path)))
    for key in _PATH_INPUTS:
        value = env.get(key, "")
        if not value:
            continue
        candidate = Path(value)
        if workspace_path is not None and not candidate.is_absolute():
            candidate = workspace_path / candidate
        candidate = _validate_path_components(candidate, key)
        if workspace_path is not None:
            candidate = Path(os.path.normpath(os.fspath(candidate)))
            try:
                candidate.relative_to(workspace_path)
            except ValueError as exc:
                raise ValueError(f"{key} must remain inside the GitHub workspace") from exc


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}

def build_argv(environ: dict[str, str] | None = None) -> list[str]:
    env = os.environ if environ is None else environ
    _validate_environment(env)
    argv = ["simulate", env.get("MZ_INPUT_PATH", "."), "--scenario", env.get("MZ_INPUT_SCENARIO", "all"), "--output", env.get("MZ_INPUT_OUTPUT", ".continuity")]
    for key, option in (("MZ_INPUT_DAYS", "--days"), ("MZ_INPUT_FAIL_UNDER", "--fail-under"), ("MZ_INPUT_BASELINE", "--baseline"), ("MZ_INPUT_METADATA", "--github-metadata"), ("MZ_INPUT_HISTORY", "--history"), ("MZ_INPUT_FALLBACK_PLAN", "--fallback-plan")):
        value = env.get(key, "").strip()
        if value:
            argv.extend((option, value))
    if _truthy(env.get("MZ_INPUT_FAIL_SCORE", "")):
        argv.append("--fail-on-score-decrease")
    if _truthy(env.get("MZ_INPUT_FAIL_HIGH", "")):
        argv.append("--fail-on-new-high-risk")
    if _truthy(env.get("MZ_INPUT_ALLOW_STALE", "")):
        argv.append("--allow-stale-github-metadata")
    return argv

def _write_outputs(environ: dict[str, str] | None = None) -> None:
    env = os.environ if environ is None else environ
    _validate_environment(env)
    output = _validate_path_components(env.get("MZ_INPUT_OUTPUT", ".continuity"), "MZ_INPUT_OUTPUT")
    output_file_value = env.get("GITHUB_OUTPUT")
    if not output_file_value:
        return
    if any(char in _CONTROL_CHARS for char in output_file_value):
        raise ValueError("GITHUB_OUTPUT contains control characters")
    output_file = Path(output_file_value)
    if not output_file.is_absolute():
        raise ValueError("GITHUB_OUTPUT must be an absolute path")
    _validate_path_components(output_file, "GITHUB_OUTPUT")
    output_file = Path(os.path.normpath(os.fspath(_absolute_path(output_file))))
    runner_temp = env.get("RUNNER_TEMP", "")
    if runner_temp:
        if any(char in _CONTROL_CHARS for char in runner_temp):
            raise ValueError("RUNNER_TEMP contains control characters")
        runner_temp_path = _validate_path_components(
            runner_temp, "RUNNER_TEMP", require_existing=True, require_directory=True
        )
        try:
            output_file.relative_to(Path(os.path.normpath(os.fspath(runner_temp_path))))
        except ValueError as exc:
            raise ValueError("GITHUB_OUTPUT must remain inside RUNNER_TEMP") from exc
    current = Path(output_file.anchor) if output_file.anchor else Path()
    parts = output_file.parts[1:] if output_file.anchor else output_file.parts
    for part in parts[:-1]:
        current /= part
        try:
            info = current.lstat()
            if _is_link_like(info):
                raise ValueError("GITHUB_OUTPUT parent path must not contain a symbolic link")
        except OSError as exc:
            raise ValueError("GITHUB_OUTPUT parent path could not be inspected") from exc
    if output_file.exists() or output_file.is_symlink():
        try:
            if _is_link_like(output_file.lstat()):
                raise ValueError("GITHUB_OUTPUT must not be a symbolic link")
        except OSError as exc:
            raise ValueError("GITHUB_OUTPUT could not be inspected") from exc
    if not output_file.parent.exists():
        raise ValueError("GITHUB_OUTPUT parent directory does not exist")
    payload = (
        f"report-directory={output}\n"
        f"report-json={output / 'continuity.json'}\n"
        f"report-markdown={output / 'report.md'}\n"
        f"report-html={output / 'report.html'}\n"
        f"recovery-directory={output / 'recovery'}\n"
        f"artifact-manifest={output / 'artifact-manifest.json'}\n"
        f"integrity-credential={output / 'continuity-credential.json'}\n"
    )
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(output_file, flags | nofollow, 0o600)
    except OSError as exc:
        raise OSError(f"could not open GITHUB_OUTPUT: {output_file}") from exc
    try:
        # O_NOFOLLOW prevents a final-component symlink on platforms that
        # implement it, but it does not prevent a hard link to another file.
        # Inspect the opened descriptor so a concurrent replacement cannot
        # redirect the write between validation and open.
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError("GITHUB_OUTPUT must be a regular file")
        if file_stat.st_nlink != 1:
            raise ValueError("GITHUB_OUTPUT must not be a hard link")
        with os.fdopen(descriptor, "a", encoding="utf-8", newline="\n") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor != -1:
            os.close(descriptor)

def run(environ: dict[str, str] | None = None) -> int:
    try:
        argv = build_argv(environ)
    except ValueError as exc:
        print(f"error: {exc}")
        return 2
    code = main(argv)
    if code == 0:
        try:
            _write_outputs(environ)
        except (OSError, ValueError) as exc:
            print(f"error: {exc}")
            return 2
    return code

if __name__ == "__main__":
    raise SystemExit(run())
