from __future__ import annotations

import argparse
import json
from pathlib import Path
from .analyzer import snapshot_repository
from .models import RepoSnapshot
from .report import write_report
from .scenarios import SCENARIOS

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="maintainer-zero", description="Chaos engineering drills for open-source continuity")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="create a starter continuity config")
    init.add_argument("path", nargs="?", default=".")
    run = sub.add_parser("simulate", aliases=["analyze"], help="run continuity drills")
    run.add_argument("path", nargs="?", default=".")
    run.add_argument("--scenario", choices=[*SCENARIOS, "all"], default=None)
    run.add_argument("--days", type=int, default=None)
    run.add_argument("--output", default=".continuity")
    run.add_argument("--fail-under", type=int, default=None, metavar="SCORE", help="exit 1 when any drill score is below SCORE (0-100)")
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
    for key in ("anonymize_people", "upload_repository_content"):
        if key in privacy and not isinstance(privacy[key], bool):
            raise ValueError(f"continuity.json privacy.{key} must be boolean")
    if privacy.get("upload_repository_content") is True:
        raise ValueError("repository uploads are not supported by the local CLI")
    return data


def _anonymize_snapshot(repo: RepoSnapshot) -> RepoSnapshot:
    """Return a stable, local-only identity mapping for report output."""
    names = sorted(repo.contributors)
    mapping = {name: f"contributor-{index}" for index, name in enumerate(names, 1)}
    owners = sorted({owner for entries in repo.codeowners.values() for owner in entries})
    owner_mapping = {owner: f"@owner-{index}" for index, owner in enumerate(owners, 1)}
    return RepoSnapshot(
        path=repo.path,
        name=repo.name,
        commits=repo.commits,
        contributors={mapping[name]: count for name, count in repo.contributors.items()},
        dependencies=repo.dependencies,
        workflows=repo.workflows,
        codeowners={pattern: [owner_mapping.get(owner, owner) for owner in entries] for pattern, entries in repo.codeowners.items()},
        release_files=repo.release_files,
    )

def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "init":
        path = Path(args.path).resolve()
        path.mkdir(parents=True, exist_ok=True)
        config = path / "continuity.json"
        if not config.exists():
            config.write_text(json.dumps({"scenarios": list(SCENARIOS), "days": 90, "privacy": {"anonymize_people": True, "upload_repository_content": False}}, indent=2), encoding="utf-8")
        print(f"Created {config}")
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
        if config.get("privacy", {}).get("anonymize_people", False):
            repo = _anonymize_snapshot(repo)
        results = [SCENARIOS[name](repo, days) for name in names]
        write_report(Path(args.output), repo, results)
    except ValueError as exc:
        print(f"error: {exc}")
        return 2
    print(f"Analyzed {repo.name}: {len(results)} drills written to {Path(args.output).resolve()}")
    for result in results:
        print(f"  {result.scenario}: {result.score}/100 ({result.confidence} confidence)")
    if fail_under is not None:
        failing = [result for result in results if result.score < fail_under]
        if failing:
            print(f"Continuity gate failed: {len(failing)} drill(s) below {fail_under}/100")
            return 1
        print(f"Continuity gate passed: all drills meet {fail_under}/100")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
