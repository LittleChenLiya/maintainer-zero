from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from maintainer_zero.baseline import BaselineError, _safe_report_file, compare_reports, gate_failed, load_report, summarize_report


def report(*, score: int, finding_id: str = "maintainer-zero.core-owner", severity: str = "high", include_workflows: bool = True) -> dict:
    repository = {
        "commits": 10,
        "contributors": {"a": 10},
        "dependencies": [],
        "codeowners": {},
        "release_files": [],
    }
    if include_workflows:
        repository["workflows"] = []
    return {
        "schema_version": 1,
        "rule_version": "0.2",
        "repository": repository,
        "results": [{
            "scenario": "maintainer-zero",
            "score": score,
            "findings": [{"finding_id": finding_id, "severity": severity, "title": "finding"}],
        }],
    }


def test_compare_reports_tracks_score_findings_and_coverage():
    comparison = compare_reports(report(score=80), report(score=70, finding_id="new-risk"))

    assert comparison["overall"] == {"baseline_score": 80, "current_score": 70, "delta": -10}
    assert comparison["scenarios"][0]["status"] == "regressed"
    assert comparison["findings"]["new_high_risk"][0]["finding_id"] == "new-risk"
    assert comparison["coverage"]["delta"] == 0
    assert comparison["gates"] == {"score_decreased": True, "new_high_risk": True}


def test_comparison_is_stable_and_distinguishes_added_scenario():
    old = report(score=80)
    current = report(score=80)
    current["results"].append({"scenario": "new-scenario", "score": 50, "findings": []})
    first = compare_reports(old, current)
    second = compare_reports(old, current)

    assert first == second
    assert first["scenarios"][1]["status"] == "added"
    assert first["scenarios"][1]["baseline_score"] is None


def test_legacy_finding_fallback_is_stable():
    old = report(score=80)
    current = report(score=80)
    del old["results"][0]["findings"][0]["finding_id"]
    del current["results"][0]["findings"][0]["finding_id"]

    comparison = compare_reports(old, current)
    assert comparison["findings"]["added"] == []
    assert comparison["findings"]["resolved"] == []


def test_existing_finding_severity_escalation_triggers_high_risk_gate():
    baseline = report(score=80, severity="medium")
    current = report(score=80, severity="high")

    comparison = compare_reports(baseline, current)

    assert comparison["findings"]["added"] == []
    assert comparison["findings"]["new_high_risk"][0]["finding_id"] == "maintainer-zero.core-owner"
    assert comparison["findings"]["new_high_risk"][0]["change"] == "severity_escalation"
    assert gate_failed(comparison, fail_on_new_high_risk=True) is True


@pytest.mark.parametrize("kwargs, expected", [
    ({"fail_on_score_decrease": True}, True),
    ({"fail_on_new_high_risk": True}, True),
    ({}, False),
])
def test_gate_failed_policies(kwargs, expected):
    comparison = compare_reports(report(score=80), report(score=70, finding_id="new-risk"))
    assert gate_failed(comparison, **kwargs) is expected


def test_load_report_rejects_future_schema_and_bad_envelope(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        load_report(path)

    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        load_report(path)


@pytest.mark.parametrize(
    "raw, message",
    [
        ('{"schema_version":1,"schema_version":1}', "duplicate"),
        ('{"schema_version":1,"rule_version":"0.2","repository":{},"results":[],"x":NaN}', "non-standard"),
    ],
)
def test_load_report_rejects_ambiguous_or_nonstandard_json(tmp_path, raw, message):
    path = tmp_path / "report.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_report(path)


def test_load_report_rejects_descriptor_redirect_before_parsing(tmp_path, monkeypatch):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report(score=80)), encoding="utf-8")
    original_fstat = os.fstat

    def mismatched_fstat(fd):
        info = original_fstat(fd)
        return SimpleNamespace(
            st_mode=info.st_mode,
            st_file_attributes=getattr(info, "st_file_attributes", 0),
            st_dev=info.st_dev,
            st_ino=info.st_ino + 1,
            st_size=info.st_size,
            st_mtime_ns=info.st_mtime_ns,
        )

    monkeypatch.setattr("maintainer_zero.baseline.os.fstat", mismatched_fstat)
    with pytest.raises(ValueError, match="changed before"):
        load_report(path)


def test_compare_reports_rejects_mixed_rule_versions():
    baseline = report(score=80)
    current = report(score=80)
    current["rule_version"] = "0.3"
    with pytest.raises(ValueError, match="different rule versions"):
        compare_reports(baseline, current)


@pytest.mark.parametrize("score", [10**1000, float("nan"), 100.5, -0.5])
def test_load_report_rejects_invalid_scores(score, tmp_path):
    payload = report(score=80)
    payload["results"][0]["score"] = score
    path = tmp_path / "invalid-score.json"
    path.write_text(json.dumps(payload, allow_nan=True), encoding="utf-8")
    with pytest.raises(ValueError, match="score|non-standard"):
        load_report(path)


def test_load_report_rejects_json_integer_digit_bomb_without_traceback(tmp_path):
    path = tmp_path / "digit-bomb.json"
    path.write_text(
        "{\"schema_version\":1,\"rule_version\":\"0.2\","
        "\"repository\":{},\"results\":[],\"value\":"
        + "9" * 5000
        + "}",
        encoding="utf-8",
    )

    with pytest.raises(BaselineError, match="Invalid continuity report"):
        load_report(path)


def test_validate_report_cli_rejects_json_integer_digit_bomb(tmp_path, capsys):
    from maintainer_zero.cli import main

    path = tmp_path / "digit-bomb.json"
    path.write_text(
        "{\"schema_version\":1,\"rule_version\":\"0.2\","
        "\"repository\":{},\"results\":[],\"value\":"
        + "9" * 5000
        + "}",
        encoding="utf-8",
    )

    assert main(["validate-report", str(path)]) == 2
    output = capsys.readouterr().out
    assert "Invalid continuity report" in output


def test_compare_reports_rejects_mixed_tool_versions():
    baseline = report(score=80)
    current = report(score=80)
    baseline["tool"] = {"name": "Maintainer-Zero", "version": "0.2.0"}
    current["tool"] = {"name": "Maintainer-Zero", "version": "0.3.0"}
    with pytest.raises(ValueError, match="different tool versions"):
        compare_reports(baseline, current)


def test_legacy_report_without_tool_metadata_remains_comparable():
    baseline = report(score=80)
    current = report(score=80)
    current["tool"] = {"name": "Maintainer-Zero", "version": "0.2.0"}
    assert compare_reports(baseline, current)["status"] == "unchanged"


def test_summarize_report_omits_repository_and_raw_findings():
    payload = report(score=80)
    payload["repository"]["path"] = "C:/private/project"
    summary = summarize_report(payload)
    assert summary["valid"] is True
    assert summary["scenario_count"] == 1
    assert summary["scenarios"][0]["score"] == 80
    assert summary["scenarios"][0]["finding_count"] == 1
    assert "repository" not in summary
    assert "finding" not in summary["scenarios"][0]


def test_validate_report_cli_reports_invalid_input(tmp_path, capsys):
    from maintainer_zero.cli import main

    path = tmp_path / "invalid-report.json"
    path.write_text("[]", encoding="utf-8")
    assert main(["validate-report", str(path)]) == 2
    assert "JSON object" in capsys.readouterr().out


def test_validate_report_cli_emits_privacy_preserving_json(tmp_path, capsys):
    from maintainer_zero.cli import main

    path = tmp_path / "report.json"
    path.write_text(json.dumps(report(score=73)), encoding="utf-8")
    assert main(["validate-report", str(path), "--format", "json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["valid"] is True
    assert output["scenarios"][0]["score"] == 73
    assert "repository" not in output


def test_summarize_report_rejects_unbounded_or_malformed_results():
    payload = report(score=80)
    payload["results"][0]["findings"] = [None]
    with pytest.raises(BaselineError, match="finding 0"):
        summarize_report(payload)

    payload = report(score=80)
    payload["results"] = [payload["results"][0]] * 101
    with pytest.raises(BaselineError, match="bounded array"):
        summarize_report(payload)


def test_summarize_report_rejects_control_characters_in_scenario():
    payload = report(score=80)
    payload["results"][0]["scenario"] = "unsafe\nscenario"
    with pytest.raises(BaselineError, match="scenario is invalid"):
        summarize_report(payload)


@pytest.mark.parametrize("field", ["rule_version", "tool_version"])
def test_summarize_report_rejects_control_characters_in_display_metadata(field):
    payload = report(score=80)
    if field == "rule_version":
        payload["rule_version"] = "0.2\nunsafe"
    else:
        payload["tool"] = {"name": "Maintainer-Zero", "version": "0.2\nunsafe"}
    with pytest.raises(BaselineError, match="non-empty string|tool metadata"):
        summarize_report(payload)


def test_summarize_report_rejects_duplicate_scenarios():
    payload = report(score=80)
    payload["results"].append(dict(payload["results"][0]))
    with pytest.raises(BaselineError, match="duplicate scenario"):
        summarize_report(payload)


def test_report_rejects_duplicate_finding_ids_before_baseline_comparison():
    payload = report(score=80)
    payload["results"][0]["findings"].append(
        {"finding_id": payload["results"][0]["findings"][0]["finding_id"], "severity": "low", "title": "duplicate"}
    )

    with pytest.raises(BaselineError, match="duplicate finding"):
        summarize_report(payload)
    with pytest.raises(BaselineError, match="duplicate finding"):
        compare_reports(report(score=80), payload)


@pytest.mark.parametrize("finding_id", [["nested"], {"id": "object"}, 42, "bad\nidentity", "x" * 129])
def test_report_rejects_malformed_present_finding_id(finding_id):
    payload = report(score=80)
    payload["results"][0]["findings"][0]["finding_id"] = finding_id

    with pytest.raises(BaselineError, match="finding 0 id is invalid"):
        summarize_report(payload)
def test_baseline_rejects_link_hidden_before_dotdot_normalization(tmp_path, monkeypatch):
    linked = tmp_path / "linked"
    linked.mkdir()
    target = linked / ".." / "report.json"
    original_lstat = Path.lstat

    def fake_lstat(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if path == linked:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(BaselineError, match="real directory"):
        _safe_report_file(target)
