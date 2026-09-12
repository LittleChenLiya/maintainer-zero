import json

import pytest

from maintainer_zero.history import MAX_HISTORY_BYTES, HistoryError, append_history, load_history, render_trend_markdown, summarize_report, trend_summary


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


def test_history_records_tool_version_and_renders_it(tmp_path):
    path = tmp_path / "versioned-history.json"
    current = report(score=80)
    current["tool"] = {"name": "Maintainer-Zero", "version": "0.2.0"}
    summary = append_history(path, current, recorded_at="2026-01-01T00:00:00Z")
    assert summary["tool_version"] == "0.2.0"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["tool_version"] == "0.2.0"
    assert payload["entries"][0]["tool_version"] == "0.2.0"
    assert "Tool version: 0.2.0" in render_trend_markdown(summary)


def test_history_rejects_mixed_tool_versions(tmp_path):
    path = tmp_path / "versioned-history.json"
    first = report(score=80)
    first["tool"] = {"name": "Maintainer-Zero", "version": "0.2.0"}
    second = report(score=81)
    second["tool"] = {"name": "Maintainer-Zero", "version": "0.3.0"}
    append_history(path, first, recorded_at="2026-01-01T00:00:00Z")
    with pytest.raises(HistoryError, match="different tool version"):
        append_history(path, second, recorded_at="2026-02-01T00:00:00Z")


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


def test_trend_includes_machine_readable_count_and_previous_deltas(tmp_path):
    path = tmp_path / "history.json"
    first = report(score=70, scenario="maintainer-zero", severity="high")
    second = report(score=75, scenario="maintainer-zero", severity="low")
    second["results"].append({"scenario": "ci-outage", "score": 60, "findings": []})
    append_history(path, first, recorded_at="2026-01-01T00:00:00Z")
    summary = append_history(path, second, recorded_at="2026-02-01T00:00:00Z")
    assert summary["rule_version"] == "0.2"
    # A newly observed scenario has no comparable prior value and is omitted.
    assert summary["scenario_delta_since_previous"] == {"maintainer-zero": 5}
    assert summary["finding_count_delta_since_previous"] == {"maintainer-zero": 0}
    assert summary["high_risk_delta_since_previous"] == -1


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda payload: payload["entries"].reverse(), "ordered by recorded_at"),
        (lambda payload: payload["entries"][0].update(rule_version="0.3"), "different rule versions"),
        (lambda payload: payload.update(repository_id="wrong"), "repository_id"),
    ],
)
def test_history_rejects_tampered_machine_contract(tmp_path, mutate, message):
    path = tmp_path / "history.json"
    append_history(path, report(score=80), recorded_at="2026-01-01T00:00:00Z")
    append_history(path, report(score=81), recorded_at="2026-02-01T00:00:00Z")
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(HistoryError, match=message):
        append_history(path, report(score=82), recorded_at="2026-03-01T00:00:00Z")


def test_append_rejects_backwards_timestamp(tmp_path):
    path = tmp_path / "history.json"
    append_history(path, report(score=80), recorded_at="2026-02-01T00:00:00Z")
    with pytest.raises(HistoryError, match="must not move backwards"):
        append_history(path, report(score=81), recorded_at="2026-01-01T00:00:00Z")

def test_append_history_uses_atomic_same_directory_replacement(tmp_path):
    path = tmp_path / "history.json"
    append_history(path, report(score=80), recorded_at="2026-01-01T00:00:00Z")
    assert not list(tmp_path.glob(".history.json.*.tmp"))
    assert json.loads(path.read_text(encoding="utf-8"))["entries"][0]["overall_score"] == 80


def test_history_rejects_symlinked_parent_for_read_and_write(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    path = linked / "history.json"
    with pytest.raises(HistoryError, match="symlink"):
        append_history(path, report(), recorded_at="2026-01-01T00:00:00Z")
    with pytest.raises(HistoryError, match="symlink"):
        from maintainer_zero.history import load_history
        load_history(path)
    assert not list(outside.iterdir())


def test_history_rejects_oversized_file_before_json_parse(tmp_path):
    path = tmp_path / "oversized-history.json"
    path.write_bytes(b"x" * (MAX_HISTORY_BYTES + 1))
    with pytest.raises(HistoryError, match="exceeds"):
        load_history(path)


def test_trend_markdown_is_path_free_and_marks_unknown_values():
    summary = trend_summary({"schema_version": 1, "repository": {"name": "repo|name", "path": "C:/private/secret"}, "entries": []})
    rendered = render_trend_markdown(summary)
    assert "repo\\|name" in rendered
    assert "C:/private/secret" not in rendered
    assert "Runs: 0" in rendered
    assert "unknown" in rendered
    assert "zero-risk" in rendered


def test_trend_markdown_escapes_scenario_table_values(tmp_path):
    path = tmp_path / "history.json"
    append_history(path, report(score=70, scenario="unsafe|scenario"), recorded_at="2026-01-01T00:00:00Z")
    append_history(path, report(score=80, scenario="unsafe|scenario"), recorded_at="2026-02-01T00:00:00Z")
    from maintainer_zero.history import load_history
    rendered = render_trend_markdown(trend_summary(load_history(path)))
    assert "unsafe\\|scenario" in rendered
    assert "| unsafe|scenario |" not in rendered


def test_history_rejects_out_of_order_and_mixed_rule_entries(tmp_path):
    path = tmp_path / "history.json"
    append_history(path, report(score=70), recorded_at="2026-02-01T00:00:00Z")
    with pytest.raises(HistoryError, match="backwards"):
        append_history(path, report(score=75), recorded_at="2026-01-01T00:00:00Z")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"][0]["overall_score"] = 101
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(HistoryError, match="0 to 100"):
        from maintainer_zero.history import load_history
        load_history(path)


def test_trend_markdown_escapes_inline_markdown_and_backslashes(tmp_path):
    path = tmp_path / "history.json"
    malicious = r"[click](https://example.invalid) `code` *emphasis* _emphasis_ <tag> \ |"
    append_history(path, report(score=70, scenario=malicious), recorded_at="2026-01-01T00:00:00Z")
    append_history(path, report(score=80, scenario=malicious), recorded_at="2026-02-01T00:00:00Z")
    from maintainer_zero.history import load_history
    rendered = render_trend_markdown(trend_summary(load_history(path)))
    assert r"\[click\]" in rendered
    assert r"\(https://example.invalid\)" in rendered
    assert r"\`code\` \*emphasis\* \_emphasis\_ \<tag\>" in rendered
    assert r"\ \|" in rendered
    assert "[click](https://example.invalid)" not in rendered
