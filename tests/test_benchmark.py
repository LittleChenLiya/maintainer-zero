from __future__ import annotations

import json
from pathlib import Path

import pytest

from maintainer_zero.benchmark import BenchmarkError, build_benchmark, render_benchmark_text
from maintainer_zero.cli import main


def report():
    return {
        "schema_version": 1,
        "tool": {"name": "Maintainer-Zero", "version": "0.2.0"},
        "rule_version": "0.2",
        "repository": {"name": "private", "path": "C:/private", "contributors": {"Alice": 9}},
        "results": [{"scenario": "ci-outage", "score": 80, "confidence": "medium", "findings": [{"severity": "high", "title": "secret finding", "detail": "raw"}]}, {"scenario": "dependency-yanked", "score": 60, "confidence": "low", "findings": []}],
        "github_metadata": {"permissions": {"issues": True, "releases": False}},
    }


def test_benchmark_omits_identity_and_raw_records():
    summary = build_benchmark(report())
    rendered = json.dumps(summary)
    assert summary["overall_score"] == 70
    assert [item["id"] for item in summary["scenarios"]] == ["ci-outage", "dependency-yanked"]
    assert summary["not_a_ranking"] is True
    assert summary["metadata"] == {"available_resources": ["issues"], "unknown_resources": ["repository", "pull_requests", "reviews", "releases"]}
    assert "private" not in rendered and "C:/private" not in rendered and "Alice" not in rendered and "secret finding" not in rendered
    assert summary["privacy"]["raw_records"] == "omitted"


def test_benchmark_rejects_duplicate_and_invalid_scenarios():
    payload = report()
    payload["results"].append(payload["results"][0].copy())
    with pytest.raises(BenchmarkError, match="duplicate"):
        build_benchmark(payload)
    payload = report()
    payload["results"][0]["score"] = 101
    with pytest.raises(BenchmarkError, match="between"):
        build_benchmark(payload)


def test_benchmark_rejects_huge_integer_without_leaking_overflow():
    payload = report()
    payload["results"][0]["score"] = 10**1000
    with pytest.raises(BenchmarkError, match="finite score"):
        build_benchmark(payload)


@pytest.mark.parametrize("score", [-0.4, 100.4])
def test_benchmark_rejects_fractional_scores_outside_range(score):
    payload = report()
    payload["results"][0]["score"] = score
    with pytest.raises(BenchmarkError, match="between"):
        build_benchmark(payload)


def test_text_renderer_rejects_untrusted_control_characters():
    with pytest.raises(BenchmarkError, match="rule_version.*control"):
        render_benchmark_text({
            "rule_version": "0.2\nInjected",
            "overall_score": None,
            "scenarios": [],
        })
    with pytest.raises(BenchmarkError, match="rule_version.*control"):
        render_benchmark_text({
            "rule_version": "0.2\u2028Injected",
            "overall_score": None,
            "scenarios": [],
        })


def test_export_benchmark_cli_writes_json_and_text(tmp_path: Path, capsys):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report()), encoding="utf-8")
    output = tmp_path / "benchmark.json"
    assert main(["export-benchmark", str(report_path), "--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["scope"] == "privacy-preserving-summary"
    text_output = tmp_path / "benchmark.txt"
    assert main(["export-benchmark", str(report_path), "--output", str(text_output), "--format", "text"]) == 0
    assert "not a ranking" in text_output.read_text(encoding="utf-8")
    assert "private" not in text_output.read_text(encoding="utf-8")
    assert "Benchmark summary written" in capsys.readouterr().out
