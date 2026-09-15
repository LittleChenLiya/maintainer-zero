from pathlib import Path
import re

from maintainer_zero.demos import load_demo_suite, run_demo_suite


ROOT = Path(__file__).parents[1]


def test_public_support_and_issue_routing_are_present():
    support = (ROOT / "SUPPORT.md").read_text(encoding="utf-8")
    issue_config = (ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml").read_text(encoding="utf-8")

    assert "GitHub Discussions" in support
    assert "SECURITY.md" in support
    assert "blank_issues_enabled: false" in issue_config
    assert "https://github.com/LittleChenLiya/maintainer-zero/discussions" in issue_config
    assert "https://github.com/LittleChenLiya/maintainer-zero/blob/main/SECURITY.md" in issue_config
    conduct = (ROOT / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8")
    assert "## Expected behavior" in conduct
    assert "## Reporting" in conduct
    assert "SECURITY.md" in conduct


def test_public_quick_start_uses_portable_source_commands_and_real_demo_output():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quick_start = readme.split("## Quick start\n", 1)[1].split("\n## ", 1)[0]
    assert "git clone https://github.com/LittleChenLiya/maintainer-zero.git" in quick_start
    assert "python -m maintainer_zero demo --fail-on-regression" in quick_start
    assert "python -m maintainer_zero simulate . --scenario all --output .continuity" in quick_start
    assert "D:\\maintainer-zero" not in quick_start
    assert "synthetic" in quick_start
    for result in run_demo_suite(load_demo_suite()):
        expected = (
            f"{result['id']} ({result['scenario']}): "
            f"{result['before_score']} -> {result['after_score']} "
            f"({result['score_delta']:+d}, improved)"
        )
        assert expected in quick_start


def test_short_launch_post_fits_and_preserves_alpha_limits():
    launch_kit = (ROOT / "docs" / "LAUNCH_KIT.md").read_text(encoding="utf-8")
    section = launch_kit.split("## X / Twitter 短帖\n", 1)[1].split("\n## ", 1)[0]
    post = section.split("~~~text\n", 1)[1].split("\n~~~", 1)[0]
    assert post.isascii()
    # X counts an HTTPS URL as 23 characters; this draft otherwise uses ASCII.
    assert len(re.sub(r"https://\S+", "x" * 23, post)) <= 280
    for boundary in ("alpha", "offline-by-default", "Heuristic",
                     "No automatic GitHub writes", "no security certification",
                     "real recovery proof"):
        assert boundary in post


def test_consumer_workflow_is_pinned_read_only_and_verifies_outputs():
    workflow = (ROOT / "examples" / "consumer-workflow.yml").read_text(encoding="utf-8")
    assert "  push:\n  pull_request:" in workflow
    assert "branches: [main]" not in workflow
    assert "  pull_request:" in workflow
    assert "  workflow_dispatch:" in workflow
    assert "    - cron: \"17 8 1 * *\"" in workflow
    assert "pull_request_target" not in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "actions/checkout@v7" in workflow
    assert "persist-credentials: false" in workflow
    assert "actions/setup-python@v7" in workflow
    assert "python-version: \"3.12\"" in workflow
    assert "runs-on: ${{ matrix.os }}" in workflow
    assert "fail-fast: false" in workflow
    assert re.search(r"matrix:\s+os: \[ubuntu-latest, windows-latest\]", workflow)
    assert "uses: LittleChenLiya/maintainer-zero@6be5c215555af557bfb1de27e61498a7e233ce00 # v0.2.2" in workflow
    assert "PYTHONPATH: ${{ steps.drill.outputs['action-path'] }}" in workflow
    assert "pull_request_target" not in workflow
    assert "python -m maintainer_zero validate-report \"$MZ_REPORT_JSON\"" in workflow
    assert "python -m maintainer_zero verify-manifest \"$MZ_MANIFEST\"" in workflow
    assert "python -m maintainer_zero verify-credential \"$MZ_CREDENTIAL\"" in workflow
    assert "Verify report and integrity artifacts (Windows)" in workflow
    assert "shell: pwsh" in workflow
    assert "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }" in workflow
    assert "Add report to job summary (Windows)" in workflow
    assert "if: always() && runner.os == 'Windows'" in workflow
    assert "if: always() && runner.os != 'Windows'" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "name: maintainer-zero-report-${{ matrix.os }}" in workflow
    assert "include-hidden-files: true" in workflow
    assert "if-no-files-found: error" in workflow
    upload = workflow.split("      - name: Upload reviewed report", 1)[1]
    assert "if: success()" in upload
    assert "if: always()" not in upload
    for artifact in (
        ".continuity/continuity.json", ".continuity/report.md",
        ".continuity/report.html", ".continuity/artifact-manifest.json",
        ".continuity/continuity-credential.json", ".continuity/recovery/runbook.md",
    ):
        assert artifact in upload


def test_consumer_workflow_checklist_covers_first_run_and_branch_boundaries():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    integration = (ROOT / "docs" / "GITHUB_INTEGRATION.md").read_text(encoding="utf-8")
    checklist = (ROOT / "docs" / "CONSUMER_WORKFLOW_CHECKLIST.md").read_text(encoding="utf-8")

    assert "docs/CONSUMER_WORKFLOW_CHECKLIST.md" in readme
    assert "CONSUMER_WORKFLOW_CHECKLIST.md" in integration
    assert "workflow_dispatch" in checklist
    assert "所有分支" in checklist
    assert "pull_request_target" in checklist
    assert "contents: read" in checklist
    assert "persist-credentials: false" in checklist
    assert "integrity credential" in checklist
    assert "alpha" in checklist
    assert "不会自动" in checklist


def test_contributor_setup_declares_yaml_test_dependency():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "[project.optional-dependencies]" in pyproject
    assert "test = [" in pyproject
    assert '"PyYAML>=6,<7"' in pyproject
    assert 'python -m pip install -e ".[test]"' in contributing
    assert 'wheel -e ".[test]"' in ci
