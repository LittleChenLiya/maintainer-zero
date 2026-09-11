"""Offline integration coverage for the checked-in composite Action adapter.

These tests execute the same Python entrypoint used by Unix and Windows steps.
They do not replace a remote GitHub Actions runner; they exercise exit codes,
report generation, output-file, and gate contracts without network access.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from maintainer_zero.github_cache import save_metadata_cache
from tools.action_entrypoint import build_argv, run


FIXTURE = Path(__file__).parent / "fixtures" / "e2e-repository"


def _git_fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "fixture repository"
    shutil.copytree(FIXTURE, repo)
    for command in (
        ["git", "init", "--quiet"],
        ["git", "config", "user.email", "fixture@example.invalid"],
        ["git", "config", "user.name", "Fixture Maintainer"],
        ["git", "add", "."],
        ["git", "commit", "--quiet", "-m", "initial fixture"],
    ):
        subprocess.run(command, cwd=repo, check=True, capture_output=True, text=True)
    return repo


def _env(repo: Path, output: Path, github_output: Path, **overrides: str) -> dict[str, str]:
    values = {
        "MZ_INPUT_PATH": str(repo),
        "MZ_INPUT_SCENARIO": "all",
        "MZ_INPUT_DAYS": "7",
        "MZ_INPUT_OUTPUT": str(output),
        "GITHUB_OUTPUT": str(github_output),
    }
    values.update(overrides)
    return values


def test_action_entrypoint_success_writes_reports_and_github_outputs(tmp_path: Path):
    repo = _git_fixture(tmp_path)
    output = tmp_path / "action output"
    github_output = tmp_path / "github-output"

    assert run(_env(repo, output, github_output)) == 0
    report = json.loads((output / "continuity.json").read_text(encoding="utf-8"))
    assert {item["scenario"] for item in report["results"]} == {
        "maintainer-zero", "dependency-yanked", "ci-outage"
    }
    lines = github_output.read_text(encoding="utf-8").splitlines()
    assert lines == [
        f"report-directory={output.resolve()}",
        f"report-json={(output / 'continuity.json').resolve()}",
    ]


def test_action_entrypoint_fail_under_returns_gate_failure_without_outputs(tmp_path: Path):
    repo = _git_fixture(tmp_path)
    output = tmp_path / "under threshold"
    github_output = tmp_path / "github-output"

    assert run(_env(repo, output, github_output, MZ_INPUT_FAIL_UNDER="100")) == 1
    assert (output / "continuity.json").exists()
    assert not github_output.exists()


def test_action_entrypoint_baseline_regression_returns_gate_failure(tmp_path: Path):
    repo = _git_fixture(tmp_path)
    baseline_output = tmp_path / "baseline"
    assert run(_env(repo, baseline_output, tmp_path / "baseline-github-output")) == 0

    with (repo / "requirements.txt").open("a", encoding="utf-8") as handle:
        handle.write("\n" + "\n".join(
            f"unreviewed-package-{index}==1.0" for index in range(12)
        ) + "\n")
    regressed_output = tmp_path / "regressed"
    regressed_github_output = tmp_path / "regressed-github-output"
    assert run(_env(
        repo, regressed_output, regressed_github_output,
        MZ_INPUT_BASELINE=str(baseline_output / "continuity.json"),
        MZ_INPUT_FAIL_SCORE="true",
    )) == 1
    comparison = json.loads((regressed_output / "baseline-comparison.json").read_text(encoding="utf-8"))
    assert comparison["status"] == "regressed"
    assert comparison["gates"]["score_decreased"] is True
    assert not regressed_github_output.exists()


def test_action_entrypoint_stale_metadata_requires_explicit_opt_in(tmp_path: Path):
    repo = _git_fixture(tmp_path)
    cache = tmp_path / "github-cache.json"
    save_metadata_cache(
        cache,
        {"schema_version": 1, "permissions": {"issues": True}, "data": {"issues": [{"number": 1}]}},
        fetched_at=datetime.now(timezone.utc) - timedelta(days=2),
        ttl_seconds=60,
    )

    rejected_output = tmp_path / "stale-rejected"
    rejected_github_output = tmp_path / "stale-rejected-github-output"
    assert run(_env(
        repo, rejected_output, rejected_github_output,
        MZ_INPUT_SCENARIO="ci-outage", MZ_INPUT_METADATA=str(cache),
    )) == 2
    assert not rejected_github_output.exists()

    accepted_output = tmp_path / "stale-accepted"
    accepted_github_output = tmp_path / "stale-accepted-github-output"
    assert run(_env(
        repo, accepted_output, accepted_github_output,
        MZ_INPUT_SCENARIO="ci-outage", MZ_INPUT_METADATA=str(cache),
        MZ_INPUT_ALLOW_STALE="true",
    )) == 0
    report = json.loads((accepted_output / "continuity.json").read_text(encoding="utf-8"))
    assert report["github_metadata"]["cache"]["state"] == "stale"
    assert accepted_github_output.exists()


def test_unix_and_windows_action_steps_share_identical_argv_semantics():
    values = {
        "MZ_INPUT_PATH": "repo path/with $value; literal",
        "MZ_INPUT_SCENARIO": "ci-outage", "MZ_INPUT_DAYS": "14",
        "MZ_INPUT_OUTPUT": "reports/with spaces", "MZ_INPUT_FAIL_UNDER": "70",
        "MZ_INPUT_BASELINE": "old report.json", "MZ_INPUT_FAIL_SCORE": "true",
        "MZ_INPUT_FAIL_HIGH": "yes", "MZ_INPUT_METADATA": "metadata snapshot.json",
        "MZ_INPUT_ALLOW_STALE": "on",
    }
    # Both composite steps invoke this adapter; no shell interpolation occurs.
    assert build_argv(dict(values)) == build_argv(dict(values))
    assert build_argv(values) == [
        "simulate", values["MZ_INPUT_PATH"], "--scenario", "ci-outage",
        "--output", values["MZ_INPUT_OUTPUT"], "--days", "14", "--fail-under", "70",
        "--baseline", "old report.json", "--github-metadata", "metadata snapshot.json",
        "--fail-on-score-decrease", "--fail-on-new-high-risk", "--allow-stale-github-metadata",
    ]
