import json

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
