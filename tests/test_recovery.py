from pathlib import Path
import json

from maintainer_zero.models import DrillResult, Finding, RepoSnapshot
from maintainer_zero.recovery import (
    render_codeowners_draft,
    render_issue_drafts,
    render_runbook,
    render_sarif,
    write_recovery_artifacts,
)


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
    assert "super-secret" not in runbook
    assert "token=[REDACTED]" in runbook
    assert "C:/private/repo" not in runbook  # path is not copied from the snapshot
    assert "<风险>" in runbook


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
    assert run["results"][0]["ruleId"] == "demo.owner"
    assert "hidden" not in json.dumps(payload)
    assert "locations" not in run["results"][0]
