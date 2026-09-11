import json
from datetime import datetime, timezone, timedelta

from maintainer_zero.cli import _build_parser
from maintainer_zero.models import DrillResult, RepoSnapshot
from maintainer_zero.report import write_report
from maintainer_zero.github_cache import save_metadata_cache
from maintainer_zero.github_metadata import MAX_METADATA_BYTES


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


def test_cli_reads_fresh_metadata_cache_and_records_source(tmp_path):
    cache = tmp_path / "github-cache.json"
    payload = {"schema_version": 1, "permissions": {"issues": True}, "data": {"issues": [{"number": 1}]}}
    save_metadata_cache(cache, payload, fetched_at=datetime.now(timezone.utc), ttl_seconds=3600)
    from maintainer_zero.cli import main

    output = tmp_path / "out"
    assert main(["simulate", ".", "--scenario", "ci-outage", "--github-metadata", str(cache), "--output", str(output)]) == 0
    report = json.loads((output / "continuity.json").read_text(encoding="utf-8"))
    assert report["github_metadata"]["cache"]["state"] == "fresh"


def test_cli_rejects_stale_metadata_cache_unless_explicit(tmp_path):
    cache = tmp_path / "github-cache.json"
    payload = {"schema_version": 1, "permissions": {"issues": True}, "data": {"issues": [{"number": 1}]}}
    save_metadata_cache(cache, payload, fetched_at=datetime.now(timezone.utc) - timedelta(days=2), ttl_seconds=60)
    from maintainer_zero.cli import main

    output = tmp_path / "out"
    assert main(["simulate", ".", "--scenario", "ci-outage", "--github-metadata", str(cache), "--output", str(output)]) == 2
    assert main(["simulate", ".", "--scenario", "ci-outage", "--github-metadata", str(cache), "--allow-stale-github-metadata", "--output", str(output)]) == 0
    report = json.loads((output / "continuity.json").read_text(encoding="utf-8"))
    assert report["github_metadata"]["cache"]["state"] == "stale"


def test_cli_rejects_oversized_cached_snapshot_before_parsing(tmp_path):
    cache = tmp_path / "oversized.json"
    cache.write_bytes(b'{"schema_version":1,"permissions":{},"data":{},"cache":{}}' + b" " * MAX_METADATA_BYTES)
    from maintainer_zero.cli import main

    assert main(["simulate", str(tmp_path), "--scenario", "ci-outage", "--github-metadata", str(cache), "--output", str(tmp_path / "out")]) == 2
