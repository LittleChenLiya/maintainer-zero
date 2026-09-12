from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from .analyzer import snapshot_repository
from .baseline import BaselineError, compare_reports, gate_failed, load_report
from .models import RepoSnapshot
from .report import write_report
from .recovery import write_recovery_artifacts
from .scenarios import SCENARIOS
from .github_metadata import MetadataError, load_metadata, summarize_metadata
from .github_cache import MetadataCacheError, cache_status, load_metadata_cache, save_metadata_cache
from .github_client import DEFAULT_MAX_RESPONSE_BYTES, GitHubClientError
from .github_collect import GitHubRepositoryError, collect_repository_metadata
from .github_http import GitHubHTTPError, GitHubHTTPTransport, HTTPTransportConfig
from .scenario_registry import ScenarioSpecError, load_registry, load_scenario, scenario_summary
from .history import HistoryError, append_history, render_trend_markdown
from .demos import DemoError, load_demo_suite, run_demo_suite
from .manifest import ManifestError, verify_manifest, write_manifest
from .fallback import FallbackPlanError, load_fallback_plan, summarize_fallback_plan
from . import __version__

def _atomic_write_text(path: str | Path, content: str) -> None:
    """Replace one local output file atomically, leaving old data on failure."""
    target = _safe_output_file(path)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _is_link_like(info: os.stat_result) -> bool:
    """Treat Windows junctions/reparse points as links as well as POSIX symlinks."""
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & reparse_flag)


def _safe_output_file(path: str | Path) -> Path:
    """Return an absolute output path with non-symlinked parent components."""
    target = Path(os.path.abspath(path))
    current = Path(target.anchor) if target.anchor else Path()
    parts = target.parts[1:] if target.anchor else target.parts
    for part in parts[:-1]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            current.mkdir()
            info = current.lstat()
        if _is_link_like(info):
            raise ValueError(f"output path may not contain a symlink: {current}")
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"output path parent is not a directory: {current}")
    if os.path.lexists(target):
        info = target.lstat()
        if _is_link_like(info):
            raise ValueError(f"output file may not be a symlink: {target}")
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"output path is not a regular file: {target}")
    return target

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="maintainer-zero", description="Chaos engineering drills for open-source continuity")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="show the installed Maintainer-Zero version and exit",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="create a starter continuity config")
    init.add_argument("path", nargs="?", default=".")
    validate = sub.add_parser("validate-scenario", help="validate a declarative scenario document without executing it")
    validate.add_argument("path")
    describe = sub.add_parser("describe-scenario", help="show a validated, non-executable scenario summary")
    describe.add_argument("path")
    describe.add_argument("--format", choices=("text", "json"), default="text", dest="describe_format")
    validate_registry = sub.add_parser("validate-registry", help="validate a versioned scenario registry without executing it")
    validate_registry.add_argument("path")
    validate_fallback = sub.add_parser("validate-fallback-plan", help="validate a data-only dependency fallback plan without executing it")
    validate_fallback.add_argument("path")
    validate_fallback.add_argument("--format", choices=("text", "json"), default="text", dest="fallback_format")
    verify = sub.add_parser("verify-manifest", help="verify a local artifact manifest without executing repository code")
    verify.add_argument("path")
    verify.add_argument("--format", choices=("text", "json"), default="text", dest="manifest_format")
    collect = sub.add_parser("collect-github", help="explicitly collect bounded, read-only GitHub metadata")
    collect.add_argument("repository", metavar="OWNER/REPOSITORY")
    collect.add_argument("--output", default="github-metadata.json", metavar="PATH")
    collect.add_argument("--allow-network", action="store_true", help="explicitly permit HTTPS GET requests")
    collect.add_argument("--allow-environment-token", action="store_true", help="explicitly allow GITHUB_TOKEN for the read-only request")
    collect.add_argument("--timeout", type=float, default=5.0, metavar="SECONDS")
    collect.add_argument("--max-pages", type=int, default=5, metavar="COUNT")
    collect.add_argument("--page-size", type=int, default=100, metavar="COUNT")
    collect.add_argument(
        "--max-response-bytes",
        type=int,
        default=DEFAULT_MAX_RESPONSE_BYTES,
        metavar="BYTES",
        help=f"maximum response body size (1-{DEFAULT_MAX_RESPONSE_BYTES}; may only reduce the default)",
    )
    collect.add_argument("--reviews-pr", type=int, default=None, metavar="NUMBER", help="explicitly collect reviews for one pull request")
    collect.add_argument("--include-repository", action="store_true", help="collect bounded repository visibility and branch metadata")
    collect.add_argument("--cache-output", default=None, metavar="PATH", help="also write a bounded local metadata cache envelope")
    collect.add_argument("--cache-ttl", type=int, default=86400, metavar="SECONDS", help="cache TTL when --cache-output is used")
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
    run.add_argument(
        "--allow-stale-github-metadata",
        action="store_true",
        help="allow an expired local GitHub metadata cache for offline review",
    )
    run.add_argument("--history", default=None, metavar="JSON", help="append a compact same-repository trend record (opt-in)")
    run.add_argument("--fallback-plan", default=None, metavar="JSON", help="use a reviewed data-only dependency fallback/cold-build plan")
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
    allowed_keys = {"scenarios", "days", "fail_under", "privacy"}
    unsupported = set(data) - allowed_keys
    if unsupported:
        raise ValueError(f"continuity.json contains unsupported fields: {', '.join(sorted(map(str, unsupported)))}")
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
    unsupported_privacy = set(privacy) - {"anonymize_people", "anonymize_repository", "upload_repository_content"}
    if unsupported_privacy:
        raise ValueError(f"continuity.json privacy contains unsupported fields: {', '.join(sorted(map(str, unsupported_privacy)))}")
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


def _load_metadata_summary(path: str | Path, *, allow_stale: bool = False) -> dict:
    """Load a plain snapshot or a bounded cache without hiding expiry.

    Plain snapshots retain their historical behavior.  A payload carrying a
    ``cache`` envelope is routed through the cache validator so an expired
    snapshot cannot silently look current in a report.
    """
    target = Path(path)
    # Use the bounded metadata reader before inspecting the envelope.  This
    # prevents cache detection from creating an unbounded JSON parsing path.
    payload = load_metadata(target)
    if "cache" in payload:
        payload = load_metadata_cache(target, allow_stale=allow_stale)
        summary = summarize_metadata(payload)
        summary["cache"] = cache_status(target).as_dict()
        return summary
    return summarize_metadata(payload)

def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "init":
        path = Path(args.path).resolve()
        path.mkdir(parents=True, exist_ok=True)
        config = path / "continuity.json"
        if not config.exists():
            try:
                _atomic_write_text(
                    config,
                    json.dumps(
                        {
                            "scenarios": list(SCENARIOS),
                            "days": 90,
                            "privacy": {
                                "anonymize_people": True,
                                "anonymize_repository": True,
                                "upload_repository_content": False,
                            },
                        },
                        indent=2,
                    )
                    + "\n",
                )
            except OSError as exc:
                print(f"error: cannot write starter config: {config}")
                return 2
        print(f"Created {config}")
        return 0
    if args.command == "collect-github":
        if not args.allow_network:
            print("error: network collection requires explicit --allow-network")
            return 2
        try:
            # Keep the default call shape compatible with injected test/integration
            # transports while propagating an explicitly tighter bound to the
            # stdlib transport itself.
            if args.max_response_bytes == DEFAULT_MAX_RESPONSE_BYTES:
                transport = GitHubHTTPTransport.from_environment(allow_environment=args.allow_environment_token)
            else:
                transport = GitHubHTTPTransport.from_environment(
                    allow_environment=args.allow_environment_token,
                    config=HTTPTransportConfig(max_response_bytes=args.max_response_bytes),
                )
            payload = collect_repository_metadata(
                args.repository,
                transport,
                timeout_seconds=args.timeout,
                max_pages=args.max_pages,
                page_size=args.page_size,
                max_response_bytes=args.max_response_bytes,
                reviews_pr=args.reviews_pr,
                include_repository=args.include_repository,
            )
            output_path = Path(args.output)
            if args.cache_output and output_path.resolve() == Path(args.cache_output).resolve():
                raise ValueError("--output and --cache-output must be different files")
            _atomic_write_text(output_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            if args.cache_output:
                save_metadata_cache(args.cache_output, payload, source="github-api", ttl_seconds=args.cache_ttl)
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
    if args.command == "describe-scenario":
        try:
            summary = scenario_summary(load_scenario(args.path))
        except ScenarioSpecError as exc:
            print(f"error: {exc}")
            return 2
        if args.describe_format == "json":
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(f"Scenario: {summary['id']} v{summary['version']}")
            print(f"Title: {summary['title']}")
            print(f"Trigger: {summary['trigger']['type']} ({summary['trigger']['duration_days']} days)")
            print("Input sources:")
            for name, source in summary["input_sources"].items():
                print(f"  - {name}: {source}")
            print("Recovery actions:")
            for action in summary["recovery_actions"]:
                print(f"  - {action}")
            print("Limitations:")
            for limitation in summary["limitations"]:
                print(f"  - {limitation}")
            print(f"Execution mode: {summary['execution_mode']}")
        return 0
    if args.command == "validate-registry":
        try:
            registry = load_registry(args.path)
        except ScenarioSpecError as exc:
            print(f"error: {exc}")
            return 2
        print(f"Valid registry: {registry['id']} v{registry['version']} ({len(registry['scenarios'])} scenarios)")
        return 0
    if args.command == "validate-fallback-plan":
        try:
            summary = summarize_fallback_plan(load_fallback_plan(args.path))
        except FallbackPlanError as exc:
            print(f"error: {exc}")
            return 2
        if args.fallback_format == "json":
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(
                f"Valid fallback plan: {summary['dependency_count']} dependencies; "
                f"execution={summary['execution']}"
            )
            for status, count in summary["cold_build_status_counts"].items():
                print(f"  cold-build {status}: {count}")
        return 0
    if args.command == "verify-manifest":
        try:
            summary = verify_manifest(args.path)
        except ManifestError as exc:
            print(f"error: {exc}")
            return 2
        if args.manifest_format == "json":
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(f"Manifest verified: {summary['verified']} artifact(s)")
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
                _atomic_write_text(output_path, rendered)
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
        privacy_summary = {
            "anonymize_people": privacy.get("anonymize_people", False) is True,
            "anonymize_repository": privacy.get("anonymize_repository", False) is True,
            "upload_repository_content": False,
        }
        if privacy.get("anonymize_people", False) or privacy.get("anonymize_repository", False):
            repo = _anonymize_snapshot(
                repo,
                anonymize_people=privacy.get("anonymize_people", False),
                anonymize_repository=privacy.get("anonymize_repository", False),
            )
        metadata_summary = None
        if args.github_metadata:
            metadata_summary = _load_metadata_summary(
                args.github_metadata, allow_stale=args.allow_stale_github_metadata
            )
        fallback_summary = None
        if args.fallback_plan:
            fallback_summary = summarize_fallback_plan(load_fallback_plan(args.fallback_plan))
        results = [SCENARIOS[name](repo, days) for name in names]
        write_report(Path(args.output), repo, results, metadata_summary, privacy_summary, fallback_summary)
        recovery_output = Path(args.recovery_output) if args.recovery_output else Path(args.output) / "recovery"
        write_recovery_artifacts(recovery_output, repo, results, privacy_summary)
        if args.history:
            history_summary = append_history(args.history, json.loads((Path(args.output) / "continuity.json").read_text(encoding="utf-8")))
            history_summary_path = Path(args.output) / "history-summary.json"
            _atomic_write_text(history_summary_path, json.dumps(history_summary, indent=2, ensure_ascii=False) + "\n")
            history_markdown_path = Path(args.output) / "history-summary.md"
            _atomic_write_text(history_markdown_path, render_trend_markdown(history_summary))
            print(f"History appended: {history_summary_path} and {history_markdown_path}")
    except (ValueError, MetadataError, MetadataCacheError, ScenarioSpecError, HistoryError, DemoError, FallbackPlanError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 2
    print(f"Analyzed {repo.name}: {len(results)} drills written to {Path(args.output).resolve()}")
    for result in results:
        print(f"  {result.scenario}: {result.score}/100 ({result.confidence} confidence)")
    baseline_failed = False
    if args.baseline:
        try:
            current_report = load_report(Path(args.output) / "continuity.json")
            comparison = compare_reports(load_report(args.baseline), current_report)
        except BaselineError as exc:
            print(f"error: {exc}")
            return 2
        comparison_path = Path(args.output) / "baseline-comparison.json"
        _atomic_write_text(comparison_path, json.dumps(comparison, indent=2, ensure_ascii=False) + "\n")
        print(f"Baseline comparison: {comparison['status']} ({comparison_path})")
        # Preserve the historical default (any regression fails) while
        # allowing repositories to opt into explicit gate policies.
        if args.fail_on_score_decrease or args.fail_on_new_high_risk:
            failed = gate_failed(comparison, fail_on_score_decrease=args.fail_on_score_decrease, fail_on_new_high_risk=args.fail_on_new_high_risk)
        else:
            failed = comparison["status"] == "regressed"
        if failed:
            print("Baseline gate failed: selected regression policy matched")
            baseline_failed = True
    manifest_artifacts = [
        Path(args.output) / "continuity.json",
        Path(args.output) / "report.md",
        Path(args.output) / "report.html",
        recovery_output / "runbook.md",
        recovery_output / "CODEOWNERS.draft",
        recovery_output / "issue-drafts.md",
        recovery_output / "continuity.sarif",
        Path(args.output) / "history-summary.json",
        Path(args.output) / "history-summary.md",
        Path(args.output) / "baseline-comparison.json",
    ]
    manifest_artifacts = [path for path in manifest_artifacts if path.exists()]
    try:
        manifest_path = write_manifest(Path(args.output), manifest_artifacts)
    except ManifestError as exc:
        print(f"error: {exc}")
        return 2
    print(f"Artifact manifest: {manifest_path}")
    if baseline_failed:
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
