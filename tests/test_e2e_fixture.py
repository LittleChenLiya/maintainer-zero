"""Offline end-to-end coverage using a tiny, real Git repository fixture."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from maintainer_zero.cli import main


FIXTURE = Path(__file__).parent / "fixtures" / "e2e-repository"


def _git_fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "fixture-repository"
    shutil.copytree(FIXTURE, repo)
    commands = [
        ["git", "init", "--quiet"],
        ["git", "config", "user.email", "fixture@example.invalid"],
        ["git", "config", "user.name", "Fixture Maintainer"],
        ["git", "add", "."],
        ["git", "commit", "--quiet", "-m", "initial fixture"],
    ]
    for command in commands:
        subprocess.run(command, cwd=repo, check=True, capture_output=True, text=True)
    return repo


def test_offline_fixture_runs_analyze_report_recovery_and_baseline_gate(tmp_path: Path):
    repo = _git_fixture(tmp_path)
    baseline_dir = tmp_path / "baseline"

    assert main(["simulate", str(repo), "--days", "7", "--output", str(baseline_dir)]) == 0
    report_path = baseline_dir / "continuity.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == 1
    assert {item["scenario"] for item in report["results"]} == {
        "maintainer-zero",
        "dependency-yanked",
        "ci-outage",
    }
    assert report["repository"]["name"] != repo.name
    assert report["repository"]["path"] == "<local-repository>"
    assert (baseline_dir / "report.md").exists()
    assert (baseline_dir / "report.html").exists()
    assert (baseline_dir / "recovery" / "runbook.md").exists()
    assert (baseline_dir / "recovery" / "CODEOWNERS.draft").exists()
    assert (baseline_dir / "recovery" / "issue-drafts.md").exists()
    assert (baseline_dir / "recovery" / "continuity.sarif").exists()

    stable_dir = tmp_path / "stable"
    assert (
        main(
            [
                "simulate",
                str(repo),
                "--days",
                "7",
                "--output",
                str(stable_dir),
                "--baseline",
                str(report_path),
                "--fail-on-score-decrease",
            ]
        )
        == 0
    )
    comparison = json.loads((stable_dir / "baseline-comparison.json").read_text(encoding="utf-8"))
    assert comparison["status"] == "unchanged"

    # A dependency explosion is an intentional negative case: the bounded
    # dependency drill score regresses and the baseline gate must fail.
    with (repo / "requirements.txt").open("a", encoding="utf-8") as handle:
        handle.write(chr(10) + chr(10).join(f"unreviewed-package-{index}==1.0" for index in range(12)) + chr(10))
    regressed_dir = tmp_path / "regressed"
    assert (
        main(
            [
                "simulate",
                str(repo),
                "--days",
                "7",
                "--output",
                str(regressed_dir),
                "--baseline",
                str(report_path),
                "--fail-on-score-decrease",
            ]
        )
        == 1
    )
    comparison = json.loads((regressed_dir / "baseline-comparison.json").read_text(encoding="utf-8"))
    assert comparison["status"] == "regressed"
    assert comparison["gates"]["score_decreased"] is True


def test_cli_history_and_baseline_sidecars_use_atomic_replacement(tmp_path: Path):
    repo = _git_fixture(tmp_path)
    first = tmp_path / "first"
    history = tmp_path / "history.json"
    assert main(["simulate", str(repo), "--days", "7", "--output", str(first), "--history", str(history)]) == 0

    second = tmp_path / "second"
    assert main([
        "simulate", str(repo), "--days", "7", "--output", str(second),
        "--baseline", str(first / "continuity.json"), "--history", str(history),
    ]) == 0
    assert (second / "history-summary.json").exists()
    assert (second / "history-summary.md").exists()
    assert "Continuity trend summary" in (second / "history-summary.md").read_text(encoding="utf-8")
    assert (second / "baseline-comparison.json").exists()
    assert not list(second.glob(".history-summary.json.*.tmp"))
    assert not list(second.glob(".baseline-comparison.json.*.tmp"))
