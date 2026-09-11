from pathlib import Path

from tools.action_entrypoint import build_argv

ROOT = Path(__file__).parents[1]

def test_composite_action_exposes_bounded_local_contract():
    action = (ROOT / "action.yml").read_text(encoding="utf-8")
    assert "using: composite" in action
    assert "report-directory:" in action and "report-json:" in action
    assert "MZ_INPUT_PATH: ${{ github.workspace }}/${{ inputs.path }}" in action
    assert "MZ_INPUT_METADATA: ${{ inputs.github-metadata }}" in action
    assert "GITHUB_TOKEN" not in action
    assert "pull_request_target" not in action
    assert "--allow-network" not in action
    assert 'python "$MZ_ACTION_PATH/tools/action_entrypoint.py"' in action
    assert 'python "$env:MZ_ACTION_PATH/tools/action_entrypoint.py"' in action
    assert "shell: pwsh" in action
    assert "if: runner.os == 'Windows'" in action
    assert "if: runner.os != 'Windows'" in action

def test_action_adapter_keeps_untrusted_paths_as_single_argv_values():
    argv = build_argv({
        "MZ_INPUT_PATH": "repo; Write-Output injected",
        "MZ_INPUT_SCENARIO": "ci-outage",
        "MZ_INPUT_OUTPUT": "reports/$value",
        "MZ_INPUT_BASELINE": "old report.json",
        "MZ_INPUT_FAIL_SCORE": "true",
    })
    assert argv == [
        "simulate", "repo; Write-Output injected", "--scenario", "ci-outage",
        "--output", "reports/$value", "--baseline", "old report.json",
        "--fail-on-score-decrease",
    ]

def test_action_adapter_emits_outputs_only_after_success(tmp_path, monkeypatch):
    from tools.action_entrypoint import _write_outputs

    output_file = tmp_path / "github-output"
    _write_outputs({"MZ_INPUT_OUTPUT": str(tmp_path / "reports"), "GITHUB_OUTPUT": str(output_file)})
    lines = output_file.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("report-directory=")
    assert lines[1].endswith("continuity.json")
