import json
from pathlib import Path
import pytest

from maintainer_zero.models import DrillResult, Finding, RepoSnapshot
from maintainer_zero.report import render_markdown, write_report


def result(detail):
    return DrillResult(
        "external", 50, "low", [], {"evidence": detail},
        [Finding("high", "unsafe", detail, "token=do-not-leak", "external.unsafe")],
        [{"day": 0, "event": detail, "impact": "secret:timeline-secret"}],
    )


def test_report_redacts_secrets_and_control_characters(tmp_path):
    repo = RepoSnapshot("C:/private/repo", "repo")
    outputs = tmp_path / "out"
    write_report(outputs, repo, [result("token=super-secret\n<!-- injected -->")])
    payload = json.loads((outputs / "continuity.json").read_text(encoding="utf-8"))
    assert payload["repository"]["path"] == "C:/private/repo"
    rendered = "\n".join([
        (outputs / "report.md").read_text(encoding="utf-8"),
        (outputs / "report.html").read_text(encoding="utf-8"),
        json.dumps(payload),
    ])
    assert "super-secret" not in rendered
    assert "timeline-secret" not in rendered
    assert "[REDACTED]" in rendered
    assert "<!-- injected -->" not in rendered

def test_report_artifacts_use_atomic_replacement_and_clean_temporary_files(tmp_path):
    outputs = tmp_path / "out"
    write_report(outputs, RepoSnapshot("C:/private/repo", "repo"), [result("safe")])
    assert not list(outputs.glob(".*.tmp"))
    assert json.loads((outputs / "continuity.json").read_text(encoding="utf-8"))["schema_version"] == 1

def test_report_write_failure_keeps_existing_artifact_intact(tmp_path, monkeypatch):
    import maintainer_zero.report as report_module
    outputs = tmp_path / "out"
    outputs.mkdir()
    existing = outputs / "continuity.json"
    existing.write_text("old report\n", encoding="utf-8")
    original_replace = report_module.os.replace

    def fail_replace(source, target):
        if Path(target) == existing:
            raise OSError("simulated replace failure")
        return original_replace(source, target)

    monkeypatch.setattr(report_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        write_report(outputs, RepoSnapshot("C:/private/repo", "repo"), [result("safe")])
    assert existing.read_text(encoding="utf-8") == "old report\n"
    assert not list(outputs.glob(".continuity.json.*.tmp"))
