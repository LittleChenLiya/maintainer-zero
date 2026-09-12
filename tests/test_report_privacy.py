import json
from pathlib import Path
import pytest

from maintainer_zero.models import DrillResult, Evidence, Finding, RepoSnapshot
from maintainer_zero.report import render_markdown, write_report
from maintainer_zero import __version__


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
    assert "### Evidence" in (outputs / "report.md").read_text(encoding="utf-8")


def test_report_records_tool_version_separately_from_rule_version(tmp_path):
    outputs = tmp_path / "versioned"
    write_report(outputs, RepoSnapshot(".", "demo"), [result("safe")])
    payload = json.loads((outputs / "continuity.json").read_text(encoding="utf-8"))
    assert payload["tool"] == {"name": "Maintainer-Zero", "version": __version__}
    assert payload["rule_version"] == "0.2"
    assert f"- **Tool version:** {chr(96)}{__version__}{chr(96)}" in (outputs / "report.md").read_text(encoding="utf-8")


def test_report_evidence_is_structured_and_sanitized(tmp_path):
    drill = DrillResult(
        "external", 50, "low", [], {}, [], [],
        [Evidence("fixture", "token", "token=secret-value", "untrusted note")],
    )
    outputs = tmp_path / "evidence"
    write_report(outputs, RepoSnapshot("C:/private/repo", "repo"), [drill])
    payload = json.loads((outputs / "continuity.json").read_text(encoding="utf-8"))
    assert payload["results"][0]["evidence"][0]["field"] == "token"
    rendered = (outputs / "report.md").read_text(encoding="utf-8")
    assert "secret-value" not in rendered
    assert "[REDACTED]" in rendered

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


def test_report_rejects_symlinked_output_parent(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="symlink"):
        write_report(linked, RepoSnapshot(".", "demo"), [result("safe")])
    assert not list(outside.iterdir())


def test_report_preflights_all_targets_before_replacement(tmp_path):
    outputs = tmp_path / "out"
    outputs.mkdir()
    existing = outputs / "continuity.json"
    existing.write_text("old report\n", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("must remain", encoding="utf-8")
    linked = outputs / "report.md"
    try:
        linked.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")

    with pytest.raises(ValueError, match="regular file"):
        write_report(outputs, RepoSnapshot(".", "demo"), [result("safe")])

    assert existing.read_text(encoding="utf-8") == "old report\n"
    assert outside.read_text(encoding="utf-8") == "must remain"
    assert not (outputs / "report.html").exists()
    assert not list(outputs.glob(".*.tmp"))


def test_report_records_privacy_boundary_without_raw_identity_values(tmp_path):
    outputs = tmp_path / "privacy-summary"
    repo = RepoSnapshot("<local-repository>", "repository-1234abcd5678", contributors={"contributor-1": 4})
    summary = {
        "anonymize_people": True,
        "anonymize_repository": True,
        "upload_repository_content": False,
    }
    write_report(outputs, repo, [result("safe")], privacy_summary=summary)

    payload = json.loads((outputs / "continuity.json").read_text(encoding="utf-8"))
    assert payload["privacy"] == summary
    rendered = "\n".join(path.read_text(encoding="utf-8") for path in outputs.iterdir())
    assert "Privacy boundary" in rendered
    assert "anonymized" in rendered
    assert "disabled" in rendered
    assert "contributor-1" in rendered
    assert "repository-1234abcd5678" in rendered
    assert "<local-repository>" in rendered


def test_report_privacy_summary_distinguishes_present_values(tmp_path):
    outputs = tmp_path / "privacy-present"
    summary = {
        "anonymize_people": False,
        "anonymize_repository": False,
        "upload_repository_content": False,
    }
    write_report(outputs, RepoSnapshot(".", "demo"), [result("safe")], privacy_summary=summary)
    markdown = (outputs / "report.md").read_text(encoding="utf-8")
    assert "Contributor and CODEOWNERS identities: **present**" in markdown
    assert "Repository name and path: **present**" in markdown
    assert json.loads((outputs / "continuity.json").read_text(encoding="utf-8"))["privacy"] == summary


def test_report_rejects_repository_content_upload_even_without_cli(tmp_path):
    with pytest.raises(ValueError, match="repository uploads are not supported"):
        write_report(
            tmp_path / "rejected",
            RepoSnapshot(".", "demo"),
            [result("safe")],
            privacy_summary={"upload_repository_content": True},
        )


def test_report_rejects_unknown_privacy_fields(tmp_path):
    with pytest.raises(ValueError, match="unsupported fields"):
        write_report(
            tmp_path / "rejected",
            RepoSnapshot(".", "demo"),
            [result("safe")],
            privacy_summary={"future_option": True},
        )


def test_report_rejects_anonymized_claim_for_raw_snapshot(tmp_path):
    output = tmp_path / "rejected"
    with pytest.raises(ValueError, match="anonymized (contributor identities|repository identity)"):
        write_report(
            output,
            RepoSnapshot("C:/private/repo", "repo", contributors={"Alice": 1}),
            [result("safe")],
            privacy_summary={"anonymize_people": True, "anonymize_repository": True},
        )
    assert not output.exists()
