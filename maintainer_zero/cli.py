from __future__ import annotations

import argparse
import json
from pathlib import Path
from .analyzer import snapshot_repository
from .report import write_report
from .scenarios import SCENARIOS

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="maintainer-zero", description="Chaos engineering drills for open-source continuity")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="create a starter continuity config")
    init.add_argument("path", nargs="?", default=".")
    run = sub.add_parser("simulate", aliases=["analyze"], help="run continuity drills")
    run.add_argument("path", nargs="?", default=".")
    run.add_argument("--scenario", choices=[*SCENARIOS, "all"], default="all")
    run.add_argument("--days", type=int, default=90)
    run.add_argument("--output", default=".continuity")
    return parser

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
        names = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
        results = [SCENARIOS[name](repo, max(1, args.days)) for name in names]
        write_report(Path(args.output), repo, results)
    except ValueError as exc:
        print(f"error: {exc}")
        return 2
    print(f"Analyzed {repo.name}: {len(results)} drills written to {Path(args.output).resolve()}")
    for result in results:
        print(f"  {result.scenario}: {result.score}/100 ({result.confidence} confidence)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
