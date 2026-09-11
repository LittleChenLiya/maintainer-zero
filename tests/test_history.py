import json

import pytest

from maintainer_zero.history import HistoryError, append_history, summarize_report, trend_summary


def report(path="D:/repo", score=80, scenario="demo", severity="low"):
    return {
        "schema_version": 1,
        "rule_version": "0.2",
        "repository": {"name": "repo", "path": path},
        "results": [{"scenario": scenario, "score": score, "findings": [{"severity": severity}]}],
    }


def test_history_keeps_only_compact_aggregates():
    summary = summarize_report(report(score=82))
    assert summary["overall_score"] == 82
    assert summary["scenarios"] == {"demo": 82}
    assert "results" not in summary


def test_append_history_and_trend_deltas(tmp_path):
    path = tmp_path / "history.json"
    append_history(path, report(score=70), recorded_at="2026-01-01T00:00:00Z")
    summary = append_history(path, report(score=85), recorded_at="2026-02-01T00:00:00Z")
    assert summary["runs"] == 2
    assert summary["delta_since_previous"] == 15
    assert summary["delta_since_first"] == 15
    assert summary["scenario_delta_since_first"] == {"demo": 15}
    assert len(json.loads(path.read_text(encoding="utf-8"))["entries"]) == 2


def test_history_rejects_mixed_repository(tmp_path):
    path = tmp_path / "history.json"
    append_history(path, report(path="D:/repo-a"), recorded_at="2026-01-01T00:00:00Z")
    with pytest.raises(HistoryError, match="different repository"):
        append_history(path, report(path="D:/repo-b"))


def test_empty_trend_is_explicit():
    payload = {"schema_version": 1, "repository": {"name": "repo", "path": "D:/repo"}, "entries": []}
    summary = trend_summary(payload)
    assert summary["runs"] == 0
    assert summary["latest"] is None
    assert summary["delta_since_first"] is None
