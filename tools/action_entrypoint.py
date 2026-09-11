"""Environment-to-argv adapter for the composite GitHub Action.

Inputs arrive through the action environment rather than shell interpolation.
"""
from __future__ import annotations

import os
from pathlib import Path

from maintainer_zero.cli import main

def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}

def build_argv(environ: dict[str, str] | None = None) -> list[str]:
    env = os.environ if environ is None else environ
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
    output = Path(env.get("MZ_INPUT_OUTPUT", ".continuity")).resolve()
    output_file = env.get("GITHUB_OUTPUT")
    if not output_file:
        return
    with open(output_file, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"report-directory={output}\n")
        handle.write(f"report-json={output / 'continuity.json'}\n")

def run(environ: dict[str, str] | None = None) -> int:
    code = main(build_argv(environ))
    if code == 0:
        _write_outputs(environ)
    return code

if __name__ == "__main__":
    raise SystemExit(run())
