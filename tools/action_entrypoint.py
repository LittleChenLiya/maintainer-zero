"""Environment-to-argv adapter for the composite GitHub Action.

Inputs arrive through the action environment rather than shell interpolation.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

from maintainer_zero.cli import main

_CONTROL_CHARS = frozenset(chr(code) for code in range(32)) | {chr(127)}
_PATH_INPUTS = ("MZ_INPUT_PATH", "MZ_INPUT_OUTPUT", "MZ_INPUT_BASELINE", "MZ_INPUT_METADATA")


def _validate_environment(env: dict[str, str]) -> None:
    """Reject control characters and workspace escapes in Action inputs."""
    for key in _PATH_INPUTS:
        if any(char in _CONTROL_CHARS for char in env.get(key, "")):
            raise ValueError(f"{key} contains control characters")
    workspace = env.get("MZ_INPUT_WORKSPACE", "").strip()
    if not workspace:
        return
    workspace_path = Path(workspace).resolve()
    for key in _PATH_INPUTS:
        value = env.get(key, "")
        if not value:
            continue
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = workspace_path / candidate
        try:
            candidate.resolve().relative_to(workspace_path)
        except ValueError as exc:
            raise ValueError(f"{key} must remain inside the GitHub workspace") from exc


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}

def build_argv(environ: dict[str, str] | None = None) -> list[str]:
    env = os.environ if environ is None else environ
    _validate_environment(env)
    argv = ["simulate", env.get("MZ_INPUT_PATH", "."), "--scenario", env.get("MZ_INPUT_SCENARIO", "all"), "--output", env.get("MZ_INPUT_OUTPUT", ".continuity")]
    for key, option in (("MZ_INPUT_DAYS", "--days"), ("MZ_INPUT_FAIL_UNDER", "--fail-under"), ("MZ_INPUT_BASELINE", "--baseline"), ("MZ_INPUT_METADATA", "--github-metadata")):
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
    output = Path(env.get("MZ_INPUT_OUTPUT", ".continuity")).resolve()
    output_file_value = env.get("GITHUB_OUTPUT")
    if not output_file_value:
        return
    if any(char in _CONTROL_CHARS for char in output_file_value):
        raise ValueError("GITHUB_OUTPUT contains control characters")
    output_file = Path(output_file_value)
    if not output_file.is_absolute():
        raise ValueError("GITHUB_OUTPUT must be an absolute path")
    runner_temp = env.get("RUNNER_TEMP", "")
    if runner_temp:
        if any(char in _CONTROL_CHARS for char in runner_temp):
            raise ValueError("RUNNER_TEMP contains control characters")
        runner_temp_path = Path(runner_temp).resolve()
        try:
            output_file.resolve().relative_to(runner_temp_path)
        except ValueError as exc:
            raise ValueError("GITHUB_OUTPUT must remain inside RUNNER_TEMP") from exc
    if output_file.exists() and output_file.is_symlink():
        raise ValueError("GITHUB_OUTPUT must not be a symbolic link")
    if not output_file.parent.exists():
        raise ValueError("GITHUB_OUTPUT parent directory does not exist")
    payload = (
        f"report-directory={output}\n"
        f"report-json={output / 'continuity.json'}\n"
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
