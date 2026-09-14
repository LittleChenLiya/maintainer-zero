from pathlib import Path
import re


WORKFLOWS = Path(__file__).parents[1] / ".github" / "workflows"
ACTION = Path(__file__).parents[1] / "action.yml"


def _matrix_values(workflow: str, key: str) -> list[str]:
    match = re.search(rf"^\s+{re.escape(key)}:\s*\[([^]]+)\]\s*$", workflow, re.MULTILINE)
    assert match, f"workflow matrix must declare {key}"
    return [value.strip().strip('\"\'') for value in match.group(1).split(",")]


def test_ci_declares_supported_cross_platform_python_matrix():
    workflow = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")

    assert _matrix_values(workflow, "os") == ["ubuntu-latest", "windows-latest"]
    assert _matrix_values(workflow, "python") == ["3.10", "3.12"]
    assert "runs-on: ${{ matrix.os }}" in workflow
    assert "python-version: ${{ matrix.python }}" in workflow
    assert "fail-fast: false" in workflow
    assert "timeout-minutes: 10" in workflow


def test_ci_preserves_repository_analysis_requirements():
    workflow = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")

    assert "permissions:\n  contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert "fetch-depth: 0" in workflow
    assert "python -m pytest -q" in workflow
    assert "python -m maintainer_zero simulate . --scenario all" in workflow


def test_ci_verifies_built_artifacts_outside_the_source_checkout():
    workflow = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")

    assert "release-smoke:" in workflow
    assert "python tools/verify_release.py --output \"$RUNNER_TEMP/maintainer-zero-release-verify\"" in workflow
    assert "python-version: \"3.12\"" in workflow


def test_workflows_have_no_write_or_untrusted_target_boundary():
    for path in WORKFLOWS.glob("*.yml"):
        workflow = path.read_text(encoding="utf-8")
        assert "pull_request_target" not in workflow, path.name
        assert not re.search(r"permissions:[\s\S]*\b(?:write|read-all|write-all)\b", workflow), path.name
        assert "persist-credentials: false" in workflow, path.name


def test_reusable_action_is_composite_and_keeps_inputs_bounded():
    action = ACTION.read_text(encoding="utf-8")

    assert "using: composite" in action
    assert "github.action_path" in action
    assert "PYTHONPATH: ${{ github.action_path }}" in action
    for input_name in ("scenario", "days", "output", "fail-under", "baseline"):
        assert f"  {input_name}:" in action
    assert "  history:" in action
    assert "  fallback-plan:" in action
    assert "MZ_INPUT_PATH: ${{ github.workspace }}" in action
    assert "MZ_INPUT_METADATA: ${{ inputs.github-metadata }}" in action
    assert 'python "$MZ_ACTION_PATH/tools/action_entrypoint.py"' in action
    assert "GITHUB_TOKEN" not in action
    assert "pull_request_target" not in action


def test_continuity_workflow_consumes_the_checked_in_action():
    workflow = (WORKFLOWS / "continuity.yml").read_text(encoding="utf-8")

    assert "uses: ./" in workflow
    assert "id: drill" in workflow
    assert "runs-on: ${{ matrix.os }}" in workflow
    assert re.search(r"matrix:\s+os: \[ubuntu-latest, windows-latest\]", workflow)
    assert "actions/setup-python@v7" in workflow
    assert "python-version: \"3.12\"" in workflow
    assert "scenario: all" in workflow
    assert "output: .continuity" in workflow
    assert "Verify Action outputs (Unix)" in workflow
    assert "Verify Action outputs (Windows)" in workflow
    assert "python -m maintainer_zero verify-manifest \"$MZ_MANIFEST\"" in workflow
    assert "python -m maintainer_zero validate-report \"$MZ_REPORT_JSON\"" in workflow
    assert "python -m maintainer_zero verify-manifest $env:MZ_MANIFEST" in workflow
    assert "python -m maintainer_zero validate-report $env:MZ_REPORT_JSON" in workflow
    for output_name in ("report-directory", "report-json", "report-markdown", "report-html", "recovery-directory", "artifact-manifest", "integrity-credential"):
        assert f"steps.drill.outputs['{output_name}']" in workflow
    assert "Publish job summary (Unix)" in workflow
    assert "Publish job summary (Windows)" in workflow
    assert "if: always() && runner.os != 'Windows'" in workflow
    assert "if: always() && runner.os == 'Windows'" in workflow
    assert "if [[ -f .continuity/report.md ]]; then" in workflow
    assert "Test-Path .continuity/report.md -PathType Leaf" in workflow
    assert "Maintainer-Zero report was not generated" in workflow
    assert "name: continuity-report-${{ matrix.os }}" in workflow
    upload = workflow.split("      - uses: actions/upload-artifact@v7", 1)[1]
    assert "if: success()" in upload
    assert "if: always()" not in upload
    assert "if-no-files-found: warn" in workflow
    assert ".continuity/artifact-manifest.json" in workflow
    assert ".continuity/continuity-credential.json" in workflow
    assert ".continuity/history-summary.json" in workflow
    assert ".continuity/history-summary.md" in workflow
    assert ".continuity/baseline-comparison.json" in workflow
    assert "verify-credential" in workflow
    for artifact in ("continuity.sarif", "runbook.md", "CODEOWNERS.draft", "issue-drafts.md"):
        assert f".continuity/recovery/{artifact}" in workflow


def test_continuity_windows_verification_propagates_each_native_exit_code():
    workflow = (WORKFLOWS / "continuity.yml").read_text(encoding="utf-8")

    windows = workflow.split("      - name: Verify Action outputs (Windows)", 1)[1].split(
        "      - name: Publish job summary (Unix)", 1
    )[0]
    assert windows.count("if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }") == 3
    for command in (
        "python -m maintainer_zero validate-report $env:MZ_REPORT_JSON",
        "python -m maintainer_zero verify-manifest $env:MZ_MANIFEST",
        "python -m maintainer_zero verify-credential $env:MZ_CREDENTIAL",
    ):
        command_position = windows.index(command)
        exit_check_position = windows.index("if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }", command_position)
        assert exit_check_position > command_position
