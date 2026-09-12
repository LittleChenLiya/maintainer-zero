from pathlib import Path
import pytest

from tools.action_entrypoint import build_argv, _write_outputs

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
    assert 'python -m pip install --disable-pip-version-check --no-deps --no-build-isolation "$env:MZ_ACTION_PATH"' in action
    assert "shell: pwsh" in action
    assert "if: runner.os == 'Windows'" in action
    assert "if: runner.os != 'Windows'" in action
    assert 'no-build-isolation "$env:MZ_ACTION_PATH"' in action

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
    output_file = tmp_path / "github-output"
    _write_outputs({"MZ_INPUT_OUTPUT": str(tmp_path / "reports"), "GITHUB_OUTPUT": str(output_file)})
    lines = output_file.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("report-directory=")
    assert lines[1].endswith("continuity.json")


def test_action_adapter_requires_runner_output_to_be_absolute_and_in_runner_temp(tmp_path):
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    output_file = runner_temp / "github-output"
    _write_outputs({
        "MZ_INPUT_OUTPUT": str(tmp_path / "reports"),
        "GITHUB_OUTPUT": str(output_file),
        "RUNNER_TEMP": str(runner_temp),
    })
    assert output_file.exists()
    with pytest.raises(ValueError, match="inside RUNNER_TEMP"):
        _write_outputs({
            "MZ_INPUT_OUTPUT": str(tmp_path / "reports"),
            "GITHUB_OUTPUT": str(tmp_path / "outside-output"),
            "RUNNER_TEMP": str(runner_temp),
        })
    with pytest.raises(ValueError, match="absolute path"):
        _write_outputs({
            "MZ_INPUT_OUTPUT": str(tmp_path / "reports"),
            "GITHUB_OUTPUT": "relative-output",
        })


def test_action_adapter_rejects_symlinked_github_output(tmp_path):
    target = tmp_path / "target"
    target.write_text("existing\n", encoding="utf-8")
    link = tmp_path / "github-output"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="symbolic link"):
        _write_outputs({"MZ_INPUT_OUTPUT": str(tmp_path / "reports"), "GITHUB_OUTPUT": str(link)})


def test_action_adapter_rejects_hardlinked_github_output(tmp_path):
    target = tmp_path / "target"
    target.write_text("keep-me\n", encoding="utf-8")
    link = tmp_path / "github-output"
    try:
        link.hardlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("hard links unavailable")
    with pytest.raises(ValueError, match="hard link"):
        _write_outputs({"MZ_INPUT_OUTPUT": str(tmp_path / "reports"), "GITHUB_OUTPUT": str(link)})
    assert target.read_text(encoding="utf-8") == "keep-me\n"


def test_action_adapter_rejects_control_characters_before_output_boundary():
    with pytest.raises(ValueError, match="control characters"):
        build_argv({"MZ_INPUT_PATH": "repo" + chr(10) + "forged-output=true"})
    with pytest.raises(ValueError, match="control characters"):
        _write_outputs({
            "MZ_INPUT_OUTPUT": "reports",
            "GITHUB_OUTPUT": "output" + chr(10) + "forged=true",
        })


def test_action_adapter_keeps_repository_and_output_below_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    argv = build_argv({
        "MZ_INPUT_WORKSPACE": str(workspace),
        "MZ_INPUT_PATH": str(workspace),
        "MZ_INPUT_OUTPUT": str(workspace / "reports"),
    })
    assert argv[1] == str(workspace)
    with pytest.raises(ValueError, match="inside the GitHub workspace"):
        build_argv({
            "MZ_INPUT_WORKSPACE": str(workspace),
            "MZ_INPUT_PATH": str(workspace.parent / "outside"),
        })

def test_action_adapter_bounds_baseline_and_metadata_to_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    argv = build_argv({
        "MZ_INPUT_WORKSPACE": str(workspace),
        "MZ_INPUT_PATH": str(workspace),
        "MZ_INPUT_OUTPUT": str(workspace / "reports"),
        "MZ_INPUT_BASELINE": "reports/old.json",
        "MZ_INPUT_METADATA": str(workspace / "metadata.json"),
    })
    assert argv[-4:] == ["--baseline", "reports/old.json", "--github-metadata", str(workspace / "metadata.json")]
    for key in ("MZ_INPUT_BASELINE", "MZ_INPUT_METADATA"):
        with pytest.raises(ValueError, match="inside the GitHub workspace"):
            build_argv({"MZ_INPUT_WORKSPACE": str(workspace), "MZ_INPUT_PATH": str(workspace), "MZ_INPUT_OUTPUT": str(workspace / "reports"), key: str(workspace.parent / "outside.json")})
