from __future__ import annotations

import json

import pytest

from maintainer_zero.baseline import compare_reports, gate_failed, load_report


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


def test_compare_reports_rejects_mixed_rule_versions():
    baseline = report(score=80)
    current = report(score=80)
    current["rule_version"] = "0.3"
    with pytest.raises(ValueError, match="different rule versions"):
        compare_reports(baseline, current)
