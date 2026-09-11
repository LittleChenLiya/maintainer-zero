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
    assert "--no-deps" in action
    assert "--no-build-isolation" in action
    for input_name in ("scenario", "days", "output", "fail-under", "baseline"):
        assert f"  {input_name}:" in action
    assert "MZ_WORKSPACE: ${{ github.workspace }}" in action
    assert "python -m maintainer_zero simulate" in action
    assert "set -euo pipefail" in action


def test_continuity_workflow_consumes_the_checked_in_action():
    workflow = (WORKFLOWS / "continuity.yml").read_text(encoding="utf-8")

    assert "uses: ./" in workflow
    assert "scenario: all" in workflow
    assert "output: .continuity" in workflow
