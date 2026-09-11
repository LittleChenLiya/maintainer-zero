import json

from maintainer_zero.cli import _build_parser
from maintainer_zero.models import DrillResult, RepoSnapshot
from maintainer_zero.report import write_report


def test_cli_accepts_metadata_snapshot():
    args = _build_parser().parse_args(["simulate", ".", "--github-metadata", "github.json"])
    assert args.github_metadata == "github.json"


def test_report_keeps_metadata_summary_without_raw_records(tmp_path):
    summary = {"source": "github-metadata", "read_only": True, "permissions": {"issues": True}, "fields": {"issues": 2, "reviews": None}, "unknown": ["reviews"]}
    result = DrillResult("demo", 80, "medium", [], {}, [], [])
    write_report(tmp_path, RepoSnapshot(".", "demo"), [result], summary)
    payload = json.loads((tmp_path / "continuity.json").read_text(encoding="utf-8"))
    assert payload["github_metadata"] == summary
    assert "GitHub metadata" in (tmp_path / "report.md").read_text(encoding="utf-8")

def test_report_explains_partial_metadata_counts(tmp_path):
    summary = {"source": "github-metadata", "read_only": True, "permissions": {"issues": True}, "fields": {"issues": 5000}, "unknown": [], "partial": ["issues"]}
    write_report(tmp_path, RepoSnapshot(".", "demo"), [DrillResult("demo", 80, "medium", [], {}, [], [])], summary)
    assert "counts are not complete" in (tmp_path / "report.md").read_text(encoding="utf-8")
