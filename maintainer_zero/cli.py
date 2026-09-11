from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from .analyzer import snapshot_repository
from .baseline import BaselineError, compare_reports, gate_failed, load_report
from .models import RepoSnapshot
from .report import write_report
from .recovery import write_recovery_artifacts
from .scenarios import SCENARIOS
from .github_metadata import MetadataError, load_metadata, summarize_metadata
from .github_client import GitHubClientError
from .github_collect import GitHubRepositoryError, collect_repository_metadata
from .github_http import GitHubHTTPError, GitHubHTTPTransport
from .scenario_registry import ScenarioSpecError, load_scenario
from .history import HistoryError, append_history
from .demos import DemoError, load_demo_suite, run_demo_suite

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="maintainer-zero", description="Chaos engineering drills for open-source continuity")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="create a starter continuity config")
    init.add_argument("path", nargs="?", default=".")
    validate = sub.add_parser("validate-scenario", help="validate a declarative scenario document without executing it")
    validate.add_argument("path")
    collect = sub.add_parser("collect-github", help="explicitly collect bounded, read-only GitHub metadata")
    collect.add_argument("repository", metavar="OWNER/REPOSITORY")
    collect.add_argument("--output", default="github-metadata.json", metavar="PATH")
    collect.add_argument("--allow-network", action="store_true", help="explicitly permit HTTPS GET requests")
    collect.add_argument("--allow-environment-token", action="store_true", help="explicitly allow GITHUB_TOKEN for the read-only request")
    collect.add_argument("--timeout", type=float, default=5.0, metavar="SECONDS")
    collect.add_argument("--max-pages", type=int, default=5, metavar="COUNT")
    collect.add_argument("--page-size", type=int, default=100, metavar="COUNT")
    collect.add_argument("--reviews-pr", type=int, default=None, metavar="NUMBER", help="explicitly collect reviews for one pull request")
    demo = sub.add_parser("demo", aliases=["demos"], help="run a bounded, data-only before/after demo suite")
    demo.add_argument("path", nargs="?", default=None, help="optional data-only demo suite; default uses the packaged suite")
    demo.add_argument("--format", choices=("text", "json"), default="text", dest="demo_format")
    demo.add_argument("--output", default=None, metavar="PATH", help="write the demo result to PATH instead of stdout")
    demo.add_argument("--fail-on-regression", action="store_true", help="return exit code 1 when any after score does not improve")
    run = sub.add_parser("simulate", aliases=["analyze"], help="run continuity drills")
    run.add_argument("path", nargs="?", default=".")
    run.add_argument("--scenario", choices=[*SCENARIOS, "all"], default=None)
    run.add_argument("--days", type=int, default=None)
    run.add_argument("--output", default=".continuity")
    run.add_argument(
        "--recovery-output",
        default=None,
        help="directory for reviewable recovery drafts (default: OUTPUT/recovery)",
    )
    run.add_argument("--fail-under", type=int, default=None, metavar="SCORE", help="exit 1 when any drill score is below SCORE (0-100)")
    run.add_argument("--baseline", default=None, metavar="JSON", help="compare with a prior continuity.json report")
    run.add_argument("--fail-on-score-decrease", action="store_true", help="fail baseline gate when a scenario score decreases")
    run.add_argument("--fail-on-new-high-risk", action="store_true", help="fail baseline gate when a new high-severity finding appears")
    run.add_argument("--github-metadata", default=None, metavar="JSON", help="use a reviewed, read-only GitHub metadata snapshot")
    run.add_argument("--history", default=None, metavar="JSON", help="append a compact same-repository trend record (opt-in)")
    return parser


def _load_config(path: Path) -> dict:
    config_path = path / "continuity.json"
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid continuity config: {config_path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Invalid continuity config: {config_path}")
    configured = data.get("scenarios")
    if "scenarios" in data:
        if isinstance(configured, str):
            configured = [configured]
        if not isinstance(configured, list) or not configured or any(not isinstance(name, str) or name not in SCENARIOS for name in configured):
            raise ValueError("continuity.json scenarios must contain known scenario names")
    days = data.get("days")
    if "days" in data and (isinstance(days, bool) or not isinstance(days, int) or days < 0):
        raise ValueError("continuity.json days must be a non-negative integer")
    fail_under = data.get("fail_under")
    if fail_under is not None and (isinstance(fail_under, bool) or not isinstance(fail_under, int) or not 0 <= fail_under <= 100):
        raise ValueError("continuity.json fail_under must be an integer from 0 to 100")
    privacy = data.get("privacy", {})
    if not isinstance(privacy, dict):
        raise ValueError("continuity.json privacy must be an object")
    for key in ("anonymize_people", "anonymize_repository", "upload_repository_content"):
        if key in privacy and not isinstance(privacy[key], bool):
            raise ValueError(f"continuity.json privacy.{key} must be boolean")
    if privacy.get("upload_repository_content") is True:
        raise ValueError("repository uploads are not supported by the local CLI")
    return data


def _anonymize_snapshot(
    repo: RepoSnapshot,
    *,
    anonymize_people: bool = True,
    anonymize_repository: bool = False,
) -> RepoSnapshot:
    """Return a stable, local-only identity mapping for report output.

    Repository identity redaction deliberately does not expose the source path or
    basename.  A short digest keeps repeated local runs joinable without making
    a private repository name or workstation path part of a shareable report.
    """
    if anonymize_people:
        names = sorted(repo.contributors)
        mapping = {name: f"contributor-{index}" for index, name in enumerate(names, 1)}
        owners = sorted({owner for entries in repo.codeowners.values() for owner in entries})
        owner_mapping = {owner: f"@owner-{index}" for index, owner in enumerate(owners, 1)}
        contributors = {mapping[name]: count for name, count in repo.contributors.items()}
        codeowners = {pattern: [owner_mapping.get(owner, owner) for owner in entries] for pattern, entries in repo.codeowners.items()}
    else:
        contributors = dict(repo.contributors)
        codeowners = {pattern: list(entries) for pattern, entries in repo.codeowners.items()}
    if anonymize_repository:
        identity = hashlib.sha256(f"{repo.name}\0{repo.path}".encode("utf-8", "replace")).hexdigest()[:12]
        name = f"repository-{identity}"
        path = "<local-repository>"
    else:
        name = repo.name
        path = repo.path
    return RepoSnapshot(
        path=path,
        name=name,
        commits=repo.commits,
        contributors=contributors,
        dependencies=repo.dependencies,
        workflows=repo.workflows,
        codeowners=codeowners,
        release_files=repo.release_files,
    )

def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "init":
        path = Path(args.path).resolve()
        path.mkdir(parents=True, exist_ok=True)
        config = path / "continuity.json"
        if not config.exists():
            config.write_text(json.dumps({"scenarios": list(SCENARIOS), "days": 90, "privacy": {"anonymize_people": True, "anonymize_repository": True, "upload_repository_content": False}}, indent=2), encoding="utf-8")
        print(f"Created {config}")
        return 0
    if args.command == "collect-github":
        if not args.allow_network:
            print("error: network collection requires explicit --allow-network")
            return 2
        try:
            transport = GitHubHTTPTransport.from_environment(allow_environment=args.allow_environment_token)
            payload = collect_repository_metadata(
                args.repository,
                transport,
                timeout_seconds=args.timeout,
                max_pages=args.max_pages,
                page_size=args.page_size,
                reviews_pr=args.reviews_pr,
            )
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except (OSError, ValueError, GitHubRepositoryError, GitHubClientError, GitHubHTTPError) as exc:
            print(f"error: {exc}")
            return 2
        available = sum(1 for value in payload["permissions"].values() if value)
        print(f"Collected read-only GitHub metadata for {args.repository}: {available}/{len(payload['permissions'])} resources available -> {output_path.resolve()}")
        return 0
    if args.command == "validate-scenario":
        try:
            scenario = load_scenario(args.path)
        except ScenarioSpecError as exc:
            print(f"error: {exc}")
            return 2
        print(f"Valid scenario: {scenario['id']} v{scenario['version']}")
        return 0
    if args.command in {"demo", "demos"}:
        try:
            suite = load_demo_suite(args.path)
            demos = run_demo_suite(suite)
        except DemoError as exc:
            print(f"error: {exc}")
            return 2
        payload = {"schema_version": 1, "results": demos}
        if args.demo_format == "json":
            rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        else:
            lines = [f"Demo suite: {len(demos)} data-only demo(s)"]
            for item in demos:
                status = "improved" if item["improved"] else "not improved"
                lines.append(
                    f"  {item['id']} ({item['scenario']}): "
                    f"{item['before_score']} -> {item['after_score']} "
                    f"({item['score_delta']:+d}, {status})"
                )
            rendered = "\n".join(lines) + "\n"
        if args.output:
            output_path = Path(args.output)
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(rendered, encoding="utf-8")
            except OSError as exc:
                print(f"error: cannot write demo output: {output_path}")
                return 2
            print(f"Demo result written to {output_path}")
        else:
            print(rendered, end="")
        if args.fail_on_regression and any(not item["improved"] for item in demos):
            print("Demo gate failed: one or more after scores did not improve")
            return 1
        return 0
    try:
        repo = snapshot_repository(args.path)
        config = _load_config(Path(args.path).resolve())
        configured_names = config.get("scenarios", list(SCENARIOS))
        if isinstance(configured_names, str):
            configured_names = [configured_names]
        if args.scenario is None:
            names = list(configured_names)
        elif args.scenario == "all":
            names = list(SCENARIOS)
        else:
            names = [args.scenario]
        days = args.days if args.days is not None else config.get("days", 90)
        if days < 0:
            raise ValueError("days must be non-negative")
        fail_under = args.fail_under if args.fail_under is not None else config.get("fail_under")
        if fail_under is not None and not 0 <= fail_under <= 100:
            raise ValueError("fail-under must be an integer from 0 to 100")
        privacy = config.get("privacy", {})
        if privacy.get("anonymize_people", False) or privacy.get("anonymize_repository", False):
            repo = _anonymize_snapshot(
                repo,
                anonymize_people=privacy.get("anonymize_people", False),
                anonymize_repository=privacy.get("anonymize_repository", False),
            )
        metadata_summary = None
        if args.github_metadata:
            metadata_summary = summarize_metadata(load_metadata(args.github_metadata))
        results = [SCENARIOS[name](repo, days) for name in names]
        write_report(Path(args.output), repo, results, metadata_summary)
        recovery_output = Path(args.recovery_output) if args.recovery_output else Path(args.output) / "recovery"
        write_recovery_artifacts(recovery_output, repo, results)
        if args.history:
            history_summary = append_history(args.history, json.loads((Path(args.output) / "continuity.json").read_text(encoding="utf-8")))
            history_summary_path = Path(args.output) / "history-summary.json"
            history_summary_path.write_text(json.dumps(history_summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"History appended: {history_summary_path}")
    except (ValueError, MetadataError, ScenarioSpecError, HistoryError, DemoError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 2
    print(f"Analyzed {repo.name}: {len(results)} drills written to {Path(args.output).resolve()}")
    for result in results:
        print(f"  {result.scenario}: {result.score}/100 ({result.confidence} confidence)")
    if args.baseline:
        try:
            current_report = load_report(Path(args.output) / "continuity.json")
            comparison = compare_reports(load_report(args.baseline), current_report)
        except BaselineError as exc:
            print(f"error: {exc}")
            return 2
        comparison_path = Path(args.output) / "baseline-comparison.json"
        comparison_path.write_text(json.dumps(comparison, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Baseline comparison: {comparison['status']} ({comparison_path})")
        # Preserve the historical default (any regression fails) while
        # allowing repositories to opt into explicit gate policies.
        if args.fail_on_score_decrease or args.fail_on_new_high_risk:
            failed = gate_failed(comparison, fail_on_score_decrease=args.fail_on_score_decrease, fail_on_new_high_risk=args.fail_on_new_high_risk)
        else:
            failed = comparison["status"] == "regressed"
        if failed:
            print("Baseline gate failed: selected regression policy matched")
            return 1
    if fail_under is not None:
        failing = [result for result in results if result.score < fail_under]
        if failing:
            print(f"Continuity gate failed: {len(failing)} drill(s) below {fail_under}/100")
            return 1
        print(f"Continuity gate passed: all drills meet {fail_under}/100")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
