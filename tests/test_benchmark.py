from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from maintainer_zero.benchmark import BenchmarkError, _safe_benchmark_file, build_benchmark, load_benchmark, render_benchmark_text, validate_benchmark
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


def test_benchmark_summary_contract_is_valid_and_deterministic(tmp_path: Path):
    summary = build_benchmark(report())
    assert validate_benchmark(summary) == summary
    path = tmp_path / "benchmark.json"
    path.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    assert load_benchmark(path) == summary


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda item: item.update({"scope": "ranking"}), "scope"),
        (lambda item: item["privacy"].update({"raw_records": "included"}), "privacy"),
        (lambda item: item["metadata"]["available_resources"].append("issues"), "duplicate"),
        (lambda item: item.update({"overall_score": 99}), "overall_score"),
    ],
)
def test_benchmark_validator_rejects_unsafe_or_inconsistent_mutations(mutator, message):
    summary = build_benchmark(report())
    mutator(summary)
    with pytest.raises(BenchmarkError, match=message):
        validate_benchmark(summary)


def test_load_benchmark_rejects_duplicate_json_keys_and_symlink(tmp_path: Path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(BenchmarkError, match="duplicate"):
        load_benchmark(path)
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(build_benchmark(report())), encoding="utf-8")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(BenchmarkError, match="regular file"):
        load_benchmark(link)


def test_validate_benchmark_rejects_unknown_fields_and_noncanonical_metadata():
    summary = build_benchmark(report())
    summary["unexpected"] = True
    with pytest.raises(BenchmarkError, match="fields"):
        validate_benchmark(summary)
    summary = build_benchmark(report())
    summary["metadata"]["available_resources"] = ["releases", "issues"]
    with pytest.raises(BenchmarkError, match="canonical"):
        validate_benchmark(summary)


@pytest.mark.parametrize("field", ["overall_score", "scenario"])
def test_validate_benchmark_rejects_fractional_canonical_scores(field):
    summary = build_benchmark(report())
    if field == "overall_score":
        summary[field] = 70.4
    else:
        summary["scenarios"][0]["score"] = 80.4
    with pytest.raises(BenchmarkError, match="integer score"):
        validate_benchmark(summary)


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


def test_export_benchmark_cli_rejects_redirected_output(tmp_path: Path, capsys):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report()), encoding="utf-8")
    outside = tmp_path / "outside.json"
    outside.write_text("keep", encoding="utf-8")
    redirected = tmp_path / "benchmark.json"
    try:
        redirected.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    assert main(["export-benchmark", str(report_path), "--output", str(redirected)]) == 2
    assert outside.read_text(encoding="utf-8") == "keep"
    assert "error:" in capsys.readouterr().out
def test_benchmark_rejects_link_hidden_before_dotdot_normalization(tmp_path, monkeypatch):
    linked = tmp_path / "linked"
    linked.mkdir()
    target = linked / ".." / "benchmark.json"
    original_lstat = Path.lstat

    def fake_lstat(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if path == linked:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(BenchmarkError, match="real directory"):
        _safe_benchmark_file(target)
