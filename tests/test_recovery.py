from pathlib import Path
import json
import pytest

from maintainer_zero.models import DrillResult, Finding, RepoSnapshot
from maintainer_zero.recovery import (
    _atomic_write_text,
    render_codeowners_draft,
    render_issue_drafts,
    render_runbook,
    render_sarif,
    write_recovery_artifacts,
)
from maintainer_zero import __version__


def _result(*, detail="核心路径 <需要复核>"):
    return DrillResult(
        scenario="demo",
        score=42,
        confidence="medium",
        assumptions=["假设维护者暂时不可用"],
        metrics={"days": 7},
        findings=[Finding("high", "单点 <风险>", detail, "指定 backup", "demo.owner")],
        timeline=[],
    )


def test_recovery_drafts_include_stable_finding_id_and_never_credentials():
    repo = RepoSnapshot(path="C:/private/repo", name="demo")
    result = _result(detail="token=super-secret")
    runbook = render_runbook(repo, [result])
    issue = render_issue_drafts(repo, [result])

    assert "demo.owner" in runbook
    assert "demo.owner" in issue
    assert "Generator version: " + chr(96) + __version__ + chr(96) in runbook
    assert "Generator version: " + chr(96) + __version__ + chr(96) in issue
    assert "super-secret" not in runbook
    assert r"token=\[REDACTED\]" in runbook
    assert "C:/private/repo" not in runbook  # path is not copied from the snapshot
    assert r"\<风险\>" in runbook


def test_recovery_markdown_escapes_structure_and_broader_credentials():
    malicious = r"[click](https://example.invalid) `code` *emphasis* <tag> authorization:secret-value"
    result = _result(detail=malicious)
    result.scenario = malicious
    result.findings[0].title = malicious
    result.findings[0].action = malicious
    runbook = render_runbook(RepoSnapshot(path=".", name=malicious), [result])
    issue = render_issue_drafts(RepoSnapshot(path=".", name=malicious), [result])
    rendered = runbook + issue
    assert "secret-value" not in rendered
    assert "[click](https://example.invalid)" not in rendered
    assert r"\[click\]\(https://example.invalid\) \`code\` \*emphasis\* \<tag\>" in rendered


def test_recovery_escapes_untrusted_finding_id_inside_code_span():
    result = _result()
    result.findings[0].finding_id = r"bad`id"
    rendered = render_runbook(RepoSnapshot(path=".", name="demo"), [result])
    assert r"bad\`id" in rendered


def test_runbook_exposes_simulated_queue_indicators_as_assumptions():
    drill = _result()
    drill.metrics.update({
        "simulated_peak_backlog": 4.0,
        "simulated_ending_backlog": 3.0,
        "simulated_service_level": 0.5,
        "simulated_recovery_day": 9,
        "simulated_recovery_ending_backlog": 0.0,
        "simulated_recovery_window_days": 7,
    })
    runbook = render_runbook(RepoSnapshot(path=".", name="demo"), [drill])
    assert "## Simulated queue indicators" in runbook
    assert "Incident peak backlog: 4.0" in runbook
    assert "not observed recovery" in runbook


def test_finding_without_id_gets_stable_slug():
    result = _result()
    result.findings[0].finding_id = ""
    first = render_issue_drafts(RepoSnapshot(path=".", name="demo"), [result])
    second = render_issue_drafts(RepoSnapshot(path=".", name="demo"), [result])
    assert first == second
    assert "demo.danger" not in first
    assert "demo." in first


def test_codeowners_draft_is_conservative_and_not_applied(tmp_path: Path):
    repo = RepoSnapshot(path=".", name="demo", codeowners={"*": ["@real-person"]})
    draft = render_codeowners_draft(repo, [])
    assert "@real-person" not in draft
    assert "NOT applied automatically" in draft
    assert "@backup-maintainer" in draft
    assert f"Generator version: {__version__}" in draft
    assert not (tmp_path / "CODEOWNERS").exists()


def test_write_recovery_artifacts_writes_only_selected_directory(tmp_path: Path):
    source = tmp_path / "repo"
    source.mkdir()
    out = tmp_path / "artifacts"
    paths = write_recovery_artifacts(out, RepoSnapshot(path=str(source), name="demo"), [_result()])
    assert [p.name for p in paths] == ["runbook.md", "CODEOWNERS.draft", "issue-drafts.md", "continuity.sarif"]
    assert all(p.parent == out and p.exists() for p in paths)
    assert not (source / "CODEOWNERS").exists()
    assert not (source / "runbook.md").exists()


def test_sarif_is_valid_and_has_no_fake_locations():
    payload = json.loads(render_sarif(RepoSnapshot(path=".", name="demo"), [_result(detail="secret=hidden")]))
    assert payload["version"] == "2.1.0"
    run = payload["runs"][0]
    assert run["tool"]["driver"]["name"] == "Maintainer-Zero"
    assert run["tool"]["driver"]["version"] == __version__
    assert run["results"][0]["ruleId"] == "demo.owner"
    assert "hidden" not in json.dumps(payload)
    assert "locations" not in run["results"][0]

def test_recovery_artifacts_use_atomic_replacement_and_clean_temporary_files(tmp_path: Path):
    out = tmp_path / "artifacts"
    write_recovery_artifacts(out, RepoSnapshot(path=".", name="demo"), [_result()])
    assert not list(out.glob(".*.tmp"))
    assert (out / "runbook.md").read_text(encoding="utf-8").startswith("# Continuity")

def test_recovery_write_failure_keeps_existing_artifact_intact(tmp_path: Path, monkeypatch):
    import maintainer_zero.recovery as recovery_module
    out = tmp_path / "artifacts"
    out.mkdir()
    existing = out / "runbook.md"
    existing.write_text("old runbook\n", encoding="utf-8")
    original_replace = recovery_module.os.replace

    def fail_replace(source, target):
        if Path(target) == existing:
            raise OSError("simulated replace failure")
        return original_replace(source, target)

    monkeypatch.setattr(recovery_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        write_recovery_artifacts(out, RepoSnapshot(path=".", name="demo"), [_result()])
    assert existing.read_text(encoding="utf-8") == "old runbook\n"


def test_recovery_rejects_symlinked_artifact_before_any_replacement(tmp_path: Path):
    out = tmp_path / "artifacts"
    out.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("must remain", encoding="utf-8")
    linked = out / "runbook.md"
    try:
        linked.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")

    with pytest.raises(ValueError, match="regular file"):
        write_recovery_artifacts(out, RepoSnapshot(path=".", name="demo"), [_result()])

    assert linked.is_symlink()
    assert outside.read_text(encoding="utf-8") == "must remain"
    assert not (out / "CODEOWNERS.draft").exists()
    assert not list(out.glob(".*.tmp"))
    assert not list(out.glob(".runbook.md.*.tmp"))


def test_recovery_set_failure_rolls_back_files_replaced_before_error(tmp_path: Path, monkeypatch):
    import maintainer_zero.recovery as recovery_module

    out = tmp_path / "artifacts"
    out.mkdir()
    filenames = ["runbook.md", "CODEOWNERS.draft", "issue-drafts.md", "continuity.sarif"]
    for filename in filenames:
        (out / filename).write_text(f"old {filename}\n", encoding="utf-8")
    original_replace = recovery_module.os.replace
    failed_target = out / "issue-drafts.md"

    def fail_mid_commit(source, target):
        if Path(target) == failed_target and str(source).endswith(".tmp"):
            raise OSError("simulated mid-set failure")
        return original_replace(source, target)

    monkeypatch.setattr(recovery_module.os, "replace", fail_mid_commit)
    with pytest.raises(OSError, match="simulated mid-set failure"):
        write_recovery_artifacts(out, RepoSnapshot(path=".", name="demo"), [_result()])
    for filename in filenames:
        assert (out / filename).read_text(encoding="utf-8") == f"old {filename}\n"
    assert not list(out.glob(".*.tmp"))
    assert not list(out.glob(".*.bak"))


def test_recovery_rejects_anonymized_claim_for_raw_snapshot(tmp_path: Path):
    output = tmp_path / "artifacts"
    with pytest.raises(ValueError, match="anonymized contributor identities"):
        write_recovery_artifacts(
            output,
            RepoSnapshot(path="C:/private/repo", name="repo", contributors={"Alice": 1}),
            [_result()],
            {"anonymize_people": True},
        )
    assert not output.exists()


def test_recovery_artifacts_expose_privacy_boundary_without_raw_identity(tmp_path: Path):
    repo = RepoSnapshot(
        path="<local-repository>",
        name="repository-1234abcd5678",
        contributors={"contributor-1": 3},
        codeowners={"*": ["@owner-1"]},
    )
    privacy = {"anonymize_people": True, "anonymize_repository": True, "upload_repository_content": False}
    output = tmp_path / "artifacts"
    write_recovery_artifacts(output, repo, [_result()], privacy)
    runbook = (output / "runbook.md").read_text(encoding="utf-8")
    issues = (output / "issue-drafts.md").read_text(encoding="utf-8")
    owners = (output / "CODEOWNERS.draft").read_text(encoding="utf-8")
    sarif = json.loads((output / "continuity.sarif").read_text(encoding="utf-8"))
    assert all("Privacy boundary" in text for text in (runbook, issues, owners))
    assert all("disabled" in text for text in (runbook, issues, owners))
    assert sarif["runs"][0]["properties"]["privacy"] == privacy
    assert "repository-1234abcd5678" in runbook
    assert "<local-repository>" not in runbook


def test_recovery_rejects_symlinked_output_directory(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "artifacts"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="may not contain a symlink"):
        write_recovery_artifacts(linked, RepoSnapshot(path=".", name="demo"), [_result()])
    assert not list(outside.iterdir())


def test_recovery_rejects_symlinked_parent_directory(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_parent = tmp_path / "linked-parent"
    try:
        linked_parent.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="may not contain a symlink"):
        write_recovery_artifacts(linked_parent / "artifacts", RepoSnapshot(path=".", name="demo"), [_result()])
    assert not list(outside.iterdir())


def test_recovery_atomic_helper_does_not_create_below_symlink_parent(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="symlink"):
        _atomic_write_text(linked / "nested" / "artifact.md", "content")
    assert not (outside / "nested").exists()
