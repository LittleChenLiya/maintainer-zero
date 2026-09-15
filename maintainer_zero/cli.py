from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from .analyzer import snapshot_repository
from .baseline import BaselineError, compare_reports, gate_failed, load_report, summarize_report
from .models import RepoSnapshot
from .report import write_report
from .recovery import write_recovery_artifacts
from .scenarios import SCENARIOS
from .github_metadata import MetadataError, load_metadata, summarize_metadata
from .github_cache import MAX_CACHE_TTL_SECONDS, MetadataCacheError, cache_status, load_metadata_cache, save_metadata_cache
from .github_client import DEFAULT_MAX_RESPONSE_BYTES, GitHubClientError
from .github_collect import GitHubRepositoryError, collect_repository_metadata
from .github_http import GitHubHTTPError, GitHubHTTPTransport, HTTPTransportConfig
from .metadata_provider import (
    DEFAULT_MAX_PAGES as DEFAULT_PROVIDER_MAX_PAGES,
    DEFAULT_PAGE_SIZE as DEFAULT_PROVIDER_PAGE_SIZE,
    DEFAULT_TIMEOUT_SECONDS as DEFAULT_PROVIDER_TIMEOUT_SECONDS,
    ProviderClientError,
    ReadOnlyProviderClient,
    validate_provider_identifier,
)
from .provider_http import (
    DEFAULT_MAX_RESPONSE_BYTES as DEFAULT_PROVIDER_MAX_RESPONSE_BYTES,
    ProviderHTTPError,
    ProviderHTTPTransport,
    ProviderHTTPTransportConfig,
)
from .scenario_registry import ScenarioSpecError, load_registry, load_scenario, scenario_summary
from .history import HistoryError, append_history, render_trend_markdown
from .demos import DemoError, load_demo_suite, run_demo_suite
from .manifest import ManifestError, verify_manifest, write_manifest
from .credential import CredentialError, create_credential, verify_credential
from .fallback import FallbackPlanError, load_fallback_plan, summarize_fallback_plan
from .benchmark import BenchmarkError, build_benchmark, load_benchmark, render_benchmark_text
from . import __version__

_MAX_CONFIG_BYTES = 1_048_576


def _reject_duplicate_config_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"continuity.json contains duplicate object key: {key}")
        result[key] = value
    return result


def _reject_nonstandard_config_number(value: str) -> None:
    raise ValueError(f"continuity.json contains non-standard JSON number: {value}")


def _open_config(path: Path):
    """Open continuity.json with bounded, fail-closed local-file checks."""
    # Preserve ``..`` until existing components have been inspected. Calling
    # ``abspath`` first would normalize ``linked/../repo`` and hide a linked
    # parent from the boundary check below.
    target = Path(path)
    if not target.is_absolute():
        target = Path.cwd() / target
    current = Path(target.anchor) if target.anchor else Path()
    parts = target.parts[1:] if target.anchor else target.parts
    for part in parts[:-1]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise ValueError("Invalid continuity config") from exc
        if _is_link_like(info):
            raise ValueError("continuity.json path may not contain a symlink or reparse point")
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("continuity.json parent must be a directory")
    target = Path(os.path.normpath(os.fspath(target)))
    try:
        initial = target.lstat()
    except FileNotFoundError:
        return None, target, None
    except OSError as exc:
        raise ValueError("Invalid continuity config") from exc
    if _is_link_like(initial) or not stat.S_ISREG(initial.st_mode):
        raise ValueError("continuity.json must be a regular file")
    if initial.st_size > _MAX_CONFIG_BYTES:
        raise ValueError(f"continuity.json exceeds {_MAX_CONFIG_BYTES} bytes")
    descriptor = None
    try:
        descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        if _is_link_like(opened) or not stat.S_ISREG(opened.st_mode):
            raise ValueError("continuity.json descriptor is not a regular file")
        identity = (getattr(initial, "st_dev", 0), getattr(initial, "st_ino", 0))
        opened_identity = (getattr(opened, "st_dev", 0), getattr(opened, "st_ino", 0))
        if opened_identity != identity:
            raise ValueError("continuity.json changed before reading")
        return os.fdopen(descriptor, "rb"), target, initial
    except ValueError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise ValueError("Invalid continuity config") from exc

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
    target = Path(path)
    if not target.is_absolute():
        target = Path.cwd() / target
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
    target = Path(os.path.normpath(os.fspath(target)))
    if os.path.lexists(target):
        info = target.lstat()
        if _is_link_like(info):
            raise ValueError(f"output file may not be a symlink: {target}")
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"output path is not a regular file: {target}")
    return target


def _safe_output_directory(path: str | Path) -> Path:
    """Create an output directory without following links or reparse points."""
    target = Path(path)
    if not target.is_absolute():
        target = Path.cwd() / target
    current = Path(target.anchor) if target.anchor else Path()
    parts = target.parts[1:] if target.anchor else target.parts
    for part in parts:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            current.mkdir()
            info = current.lstat()
        if _is_link_like(info):
            raise ValueError(f"output directory may not contain a symlink or reparse point: {current}")
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"output path is not a directory: {current}")
    return Path(os.path.normpath(os.fspath(target)))


def _lexical_absolute_path(path: str | Path) -> Path:
    """Normalize a user path without resolving symlinks or reparse points."""
    target = Path(path)
    if not target.is_absolute():
        target = Path.cwd() / target
    return Path(os.path.normpath(os.fspath(target)))


def _same_or_nested_path(parent: Path, candidate: Path) -> bool:
    """Compare lexical paths while respecting platform case rules."""
    parent_text = os.path.normcase(os.path.normpath(os.fspath(parent)))
    candidate_text = os.path.normcase(os.path.normpath(os.fspath(candidate)))
    try:
        return os.path.commonpath((parent_text, candidate_text)) == parent_text
    except ValueError:
        # Different Windows drives (or malformed mixed path flavors) cannot
        # overlap, and must not make a preflight check fail open.
        return False


def _validate_simulation_output_paths(args: argparse.Namespace) -> None:
    """Reject output-path collisions before simulation mutates any artifact.

    ``simulate`` writes a fixed set of report, recovery, manifest, and
    credential files.  A caller-controlled history path must remain free to
    live alongside those files (for example ``.continuity/history.json``),
    but must never alias one of them.  Recovery output may be customized, so
    also reject a recovery directory that would be nested below a path the
    report generation is about to replace.
    """
    output_root = _lexical_absolute_path(args.output)
    recovery_root = _lexical_absolute_path(
        args.recovery_output if args.recovery_output else output_root / "recovery"
    )
    output_files = [
        output_root / "continuity.json",
        output_root / "report.md",
        output_root / "report.html",
        output_root / "artifact-manifest.json",
        output_root / "continuity-credential.json",
    ]
    if args.history:
        output_files.extend((output_root / "history-summary.json", output_root / "history-summary.md"))
    if args.baseline:
        output_files.append(output_root / "baseline-comparison.json")
    recovery_files = [
        recovery_root / "runbook.md",
        recovery_root / "CODEOWNERS.draft",
        recovery_root / "issue-drafts.md",
        recovery_root / "continuity.sarif",
    ]

    # A recovery root cannot be a file that report/manifest/credential output
    # will replace, nor a descendant of one (e.g. OUTPUT/continuity.json/x).
    # The latter matters when the named artifact does not exist yet: creating
    # the nested recovery directory would otherwise fail only after reports
    # have already replaced older output.
    for target in output_files:
        if _same_or_nested_path(target, recovery_root):
            raise ValueError("recovery output collides with a generated artifact path")

    if args.history:
        history_path = _lexical_absolute_path(args.history)
        if history_path == output_root:
            raise ValueError("history output collides with the report output directory")
        if history_path == recovery_root:
            raise ValueError("history output collides with the recovery output directory")
        for target in output_files + recovery_files:
            if _same_or_nested_path(target, history_path) or _same_or_nested_path(history_path, target):
                raise ValueError("history output collides with a generated artifact path")


def _output_paths_collide(left: str | Path, right: str | Path) -> bool:
    """Compare destinations lexically without following filesystem links."""
    def lexical(value: str | Path) -> str:
        return os.path.normcase(os.path.normpath(os.path.abspath(os.fspath(value))))

    return lexical(left) == lexical(right)

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
    validate_metadata = sub.add_parser("validate-metadata", help="validate a read-only provider-neutral metadata snapshot without executing it")
    validate_metadata.add_argument("path")
    validate_metadata.add_argument("--format", choices=("text", "json"), default="text", dest="metadata_format")
    benchmark = sub.add_parser("export-benchmark", help="export a privacy-preserving benchmark summary from a report")
    benchmark.add_argument("report", metavar="REPORT")
    benchmark.add_argument("--output", required=True, metavar="PATH")
    benchmark.add_argument("--format", choices=("json", "text"), default="json", dest="benchmark_format")
    validate_benchmark = sub.add_parser("validate-benchmark", help="validate a privacy-preserving benchmark summary without executing code")
    validate_benchmark.add_argument("path")
    validate_benchmark.add_argument("--format", choices=("json", "text"), default="text", dest="benchmark_validate_format")
    validate_report = sub.add_parser("validate-report", help="validate a continuity report without executing repository code")
    validate_report.add_argument("path")
    validate_report.add_argument("--format", choices=("text", "json"), default="text", dest="report_validate_format")
    verify = sub.add_parser("verify-manifest", help="verify a local artifact manifest without executing repository code")
    verify.add_argument("path")
    verify.add_argument("--format", choices=("text", "json"), default="text", dest="manifest_format")
    credential = sub.add_parser("verify-credential", help="verify an offline integrity credential without executing repository code")
    credential.add_argument("path")
    credential.add_argument("--format", choices=("text", "json"), default="text", dest="credential_format")
    create_credential_parser = sub.add_parser("create-credential", help="create an offline integrity credential for an existing report and manifest")
    create_credential_parser.add_argument("report")
    create_credential_parser.add_argument("manifest")
    create_credential_parser.add_argument("--output", default=None, metavar="PATH")
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
    provider_collect = sub.add_parser(
        "collect-provider",
        help="explicitly collect bounded, read-only GitLab or Forgejo metadata",
    )
    provider_collect.add_argument("provider", choices=("gitlab", "forgejo"))
    provider_collect.add_argument("identifier", metavar="PROJECT_OR_OWNER/REPOSITORY")
    provider_collect.add_argument("--api-base", required=True, metavar="HTTPS_URL", help="provider API base URL (HTTPS only)")
    provider_collect.add_argument("--output", default=None, metavar="PATH")
    provider_collect.add_argument("--allow-network", action="store_true", help="explicitly permit HTTPS GET requests")
    provider_collect.add_argument("--allow-environment-token", action="store_true", help="explicitly allow the provider token environment variable")
    provider_collect.add_argument("--timeout", type=float, default=DEFAULT_PROVIDER_TIMEOUT_SECONDS, metavar="SECONDS")
    provider_collect.add_argument("--max-pages", type=int, default=DEFAULT_PROVIDER_MAX_PAGES, metavar="COUNT")
    provider_collect.add_argument("--page-size", type=int, default=DEFAULT_PROVIDER_PAGE_SIZE, metavar="COUNT")
    provider_collect.add_argument(
        "--max-response-bytes",
        type=int,
        default=DEFAULT_PROVIDER_MAX_RESPONSE_BYTES,
        metavar="BYTES",
        help=f"maximum response body size (1-{DEFAULT_PROVIDER_MAX_RESPONSE_BYTES})",
    )
    provider_collect.add_argument("--reviews-pr", type=int, default=None, metavar="NUMBER", help="explicitly collect reviews for one pull request")
    provider_collect.add_argument("--include-repository", action="store_true", help="collect bounded repository/project metadata")
    provider_collect.add_argument("--cache-output", default=None, metavar="PATH", help="also write a bounded local metadata cache envelope")
    provider_collect.add_argument("--cache-ttl", type=int, default=86400, metavar="SECONDS", help="cache TTL when --cache-output is used")
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
    handle, target, initial = _open_config(config_path)
    if handle is None:
        return {}
    try:
        with handle:
            raw = handle.read(_MAX_CONFIG_BYTES + 1)
        if len(raw) > _MAX_CONFIG_BYTES:
            raise ValueError(f"continuity.json exceeds {_MAX_CONFIG_BYTES} bytes")
        try:
            after = target.lstat()
        except OSError as exc:
            raise ValueError(f"Invalid continuity config: {config_path}") from exc
        identity = (getattr(initial, "st_dev", 0), getattr(initial, "st_ino", 0))
        after_identity = (getattr(after, "st_dev", 0), getattr(after, "st_ino", 0))
        if (
            _is_link_like(after)
            or not stat.S_ISREG(after.st_mode)
            or after_identity != identity
            or after.st_size != initial.st_size
            or getattr(after, "st_mtime_ns", None) != getattr(initial, "st_mtime_ns", None)
        ):
            raise ValueError("continuity.json changed during reading")
        data = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_config_keys,
            parse_constant=_reject_nonstandard_config_number,
        )
    except ValueError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
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
        try:
            # Keep the user-supplied spelling until every path component has
            # been inspected. Resolving first would follow a symlink and
            # allow starter configuration to be written outside the target.
            path = _safe_output_directory(args.path)
            config = path / "continuity.json"
            # ``Path.exists()`` follows links and returns false for dangling
            # links.  Validate the target by identity first so an existing
            # link or special file cannot be silently treated as a preserved
            # user configuration.
            _safe_output_file(config)
            if not os.path.lexists(config):
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
        except (OSError, ValueError):
            print(f"error: cannot write starter config: {Path(os.path.abspath(args.path)) / 'continuity.json'}")
            return 2
        print(f"Created {config}")
        return 0
    if args.command == "collect-github":
        if not args.allow_network:
            print("error: network collection requires explicit --allow-network")
            return 2
        output_path = Path(args.output)
        try:
            # Validate local destinations before constructing a transport or
            # making any network request.  An unsafe output path must fail
            # closed without consuming the explicitly granted read budget.
            _safe_output_file(output_path)
            if args.cache_output:
                _safe_output_file(args.cache_output)
            if args.cache_output and _output_paths_collide(output_path, args.cache_output):
                raise ValueError("--output and --cache-output must be different files")
        except (OSError, ValueError) as exc:
            print(f"error: {exc}")
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
            if args.cache_output and _output_paths_collide(output_path, args.cache_output):
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
    if args.command == "collect-provider":
        if not args.allow_network:
            print("error: network collection requires explicit --allow-network")
            return 2
        output_path = Path(args.output or f"{args.provider}-metadata.json")
        try:
            # Validate all user-controlled bounds and URL/identifier policy
            # before constructing a transport (and therefore before any I/O).
            validate_provider_identifier(args.provider, args.identifier)
            # ``urlsplit`` deliberately strips some C0 controls.  Reject them
            # explicitly so an injected transport cannot bypass the HTTPS
            # transport's header/path safety checks.
            if not isinstance(args.api_base, str) or any(
                ord(char) < 32 or ord(char) == 127 for char in args.api_base
            ):
                raise ProviderHTTPError("api_base must be an https URL without a trailing slash")
            parsed_base = urlsplit(args.api_base)
            if (
                parsed_base.scheme != "https"
                or not parsed_base.hostname
                or parsed_base.username is not None
                or parsed_base.password is not None
                or parsed_base.query
                or parsed_base.fragment
                or args.api_base.endswith("/")
            ):
                raise ProviderHTTPError("api_base must be an https URL without a trailing slash")
            if (
                isinstance(args.timeout, bool)
                or not isinstance(args.timeout, (int, float))
                or not math.isfinite(args.timeout)
                or not 0 < args.timeout <= 60
            ):
                raise ProviderClientError("timeout must be finite and in (0, 60] seconds")
            if not 1 <= args.max_pages <= 50:
                raise ProviderClientError("max_pages must be an integer from 1 to 50")
            if not 1 <= args.page_size <= 100:
                raise ProviderClientError("page_size must be an integer from 1 to 100")
            if not 1 <= args.max_response_bytes <= DEFAULT_PROVIDER_MAX_RESPONSE_BYTES:
                raise ProviderClientError(
                    f"max_response_bytes must be an integer from 1 to {DEFAULT_PROVIDER_MAX_RESPONSE_BYTES}"
                )
            if args.cache_output is not None and (
                isinstance(args.cache_ttl, bool)
                or not isinstance(args.cache_ttl, int)
                or not 1 <= args.cache_ttl <= MAX_CACHE_TTL_SECONDS
            ):
                raise ProviderClientError(
                    f"cache_ttl must be an integer from 1 to {MAX_CACHE_TTL_SECONDS}"
                )
            config = ProviderHTTPTransportConfig(
                api_base=args.api_base,
                max_response_bytes=args.max_response_bytes,
            )
            # Check output targets and collisions before collecting.  This
            # prevents a network request when local destination policy already
            # guarantees failure, and preserves atomic-output semantics.
            if args.cache_output and _output_paths_collide(output_path, args.cache_output):
                raise ValueError("--output and --cache-output must be different files")
            _safe_output_file(output_path)
            if args.cache_output:
                _safe_output_file(args.cache_output)
            transport = ProviderHTTPTransport.from_environment(
                args.provider,
                allow_environment=args.allow_environment_token,
                config=config,
            )
            client = ReadOnlyProviderClient(
                args.provider,
                transport,
                timeout_seconds=args.timeout,
                max_pages=args.max_pages,
                page_size=args.page_size,
                max_response_bytes=args.max_response_bytes,
            )
            payload = client.collect(
                args.identifier,
                include_repository=args.include_repository,
                reviews_pr=args.reviews_pr,
            )
            _atomic_write_text(output_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            if args.cache_output:
                save_metadata_cache(
                    args.cache_output,
                    payload,
                    source=f"{args.provider}-api",
                    ttl_seconds=args.cache_ttl,
                )
        except (OSError, ValueError, ProviderClientError, ProviderHTTPError, MetadataCacheError) as exc:
            print(f"error: {exc}")
            return 2
        available = sum(1 for value in payload["permissions"].values() if value)
        print(
            f"Collected read-only {args.provider} metadata for {args.identifier}: "
            f"{available}/{len(payload['permissions'])} resources available -> {output_path.resolve()}"
        )
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
    if args.command == "validate-metadata":
        try:
            summary = summarize_metadata(load_metadata(args.path))
        except MetadataError as exc:
            print(f"error: {exc}")
            return 2
        if args.metadata_format == "json":
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            provider = summary.get("provider", "github")
            print(f"Valid {provider} metadata snapshot: {len(summary['unknown'])} unknown resource(s)")
            if summary.get("partial"):
                print(f"  partial: {', '.join(summary['partial'])}")
        return 0
    if args.command == "export-benchmark":
        try:
            summary = build_benchmark(load_report(args.report))
            rendered = (
                json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
                if args.benchmark_format == "json"
                else render_benchmark_text(summary)
            )
            _atomic_write_text(args.output, rendered)
        except (BaselineError, BenchmarkError, OSError, ValueError) as exc:
            print(f"error: {exc}")
            return 2
        print(f"Benchmark summary written to {Path(args.output).resolve()}")
        return 0
    if args.command == "validate-benchmark":
        try:
            summary = load_benchmark(args.path)
        except BenchmarkError as exc:
            print(f"error: {exc}")
            return 2
        if args.benchmark_validate_format == "json":
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(
                f"Valid benchmark: {len(summary['scenarios'])} scenario(s); "
                f"overall_score={summary['overall_score'] if summary['overall_score'] is not None else 'unknown'}; "
                "scope=privacy-preserving-summary; not_a_ranking=true"
            )
        return 0
    if args.command == "validate-report":
        try:
            summary = summarize_report(load_report(args.path))
        except BaselineError as exc:
            print(f"error: {exc}")
            return 2
        if args.report_validate_format == "json":
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(
                f"Valid continuity report: {summary['scenario_count']} scenario(s); "
                f"schema={summary['schema_version']}; rule={summary['rule_version']}"
            )
            for item in summary["scenarios"]:
                label = item["id"] or f"index-{item['index']}"
                score = item["score"] if item["score"] is not None else "unknown"
                print(f"  {label}: score={score}; findings={item['finding_count'] if item['finding_count'] is not None else 'unknown'}")
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
    if args.command == "verify-credential":
        try:
            summary = verify_credential(args.path)
        except (CredentialError, OSError, ValueError) as exc:
            print(f"error: {exc}")
            return 2

        if args.credential_format == "json":
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(f"Credential verified: {summary['report']} + {summary['manifest']}")
        return 0
    if args.command == "create-credential":
        try:
            path = create_credential(args.report, args.manifest, args.output)
        except CredentialError as exc:
            print(f"error: {exc}")
            return 2
        print(f"Integrity credential written to {path.resolve()}")
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
                _atomic_write_text(output_path, rendered)
            except (OSError, ValueError) as exc:
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
        _validate_simulation_output_paths(args)
        output_root = _lexical_absolute_path(args.output)
        recovery_output = (
            _lexical_absolute_path(args.recovery_output)
            if args.recovery_output
            else output_root / "recovery"
        )
        repo = snapshot_repository(args.path)
        # Keep the repository spelling intact until the config reader performs
        # its component-by-component no-follow inspection.
        config = _load_config(Path(args.path))
        # Load the baseline before writing the new report.  This is important
        # for the documented in-place workflow where --baseline points at the
        # previous output/continuity.json; report generation atomically replaces
        # that path before the comparison phase below.
        baseline_report = load_report(args.baseline) if args.baseline else None
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
        write_report(output_root, repo, results, metadata_summary, privacy_summary, fallback_summary)
        write_recovery_artifacts(recovery_output, repo, results, privacy_summary)
        if args.history:
            history_summary = append_history(args.history, load_report(output_root / "continuity.json"))
            history_summary_path = output_root / "history-summary.json"
            _atomic_write_text(history_summary_path, json.dumps(history_summary, indent=2, ensure_ascii=False) + "\n")
            history_markdown_path = output_root / "history-summary.md"
            _atomic_write_text(history_markdown_path, render_trend_markdown(history_summary))
            print(f"History appended: {history_summary_path} and {history_markdown_path}")
    except (ValueError, MetadataError, MetadataCacheError, ScenarioSpecError, HistoryError, DemoError, FallbackPlanError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 2
    print(f"Analyzed {repo.name}: {len(results)} drills written to {output_root}")
    for result in results:
        print(f"  {result.scenario}: {result.score}/100 ({result.confidence} confidence)")
    baseline_failed = False
    if args.baseline:
        try:
            current_report = load_report(output_root / "continuity.json")
            comparison = compare_reports(baseline_report, current_report)
        except BaselineError as exc:
            print(f"error: {exc}")
            return 2
        comparison_path = output_root / "baseline-comparison.json"
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
        output_root / "continuity.json",
        output_root / "report.md",
        output_root / "report.html",
        recovery_output / "runbook.md",
        recovery_output / "CODEOWNERS.draft",
        recovery_output / "issue-drafts.md",
        recovery_output / "continuity.sarif",
        output_root / "history-summary.json",
        output_root / "history-summary.md",
        output_root / "baseline-comparison.json",
    ]
    # The core report/recovery artifacts are mandatory: never drop one merely
    # because a concurrent deletion made ``exists()`` false. Optional trend
    # sidecars are included only when present, while dangling links and special
    # files remain in the candidate set so ``write_manifest`` rejects them.
    mandatory_artifacts = manifest_artifacts[:7]
    optional_artifacts = [path for path in manifest_artifacts[7:] if os.path.lexists(path)]
    manifest_artifacts = mandatory_artifacts + optional_artifacts
    try:
        manifest_path = write_manifest(output_root, manifest_artifacts)
    except ManifestError as exc:
        print(f"error: {exc}")
        return 2
    print(f"Artifact manifest: {manifest_path}")
    try:
        credential_path = create_credential(
            output_root / "continuity.json",
            manifest_path,
        )
    except CredentialError as exc:
        print(f"error: {exc}")
        return 2
    print(f"Integrity credential: {credential_path}")
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
