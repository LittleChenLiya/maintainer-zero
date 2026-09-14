from pathlib import Path
import os
import stat
from types import SimpleNamespace
import pytest

from tools.action_entrypoint import build_argv, _write_outputs

ROOT = Path(__file__).parents[1]

def test_composite_action_exposes_bounded_local_contract():
    action = (ROOT / "action.yml").read_text(encoding="utf-8")
    assert "using: composite" in action
    assert all(name in action for name in ("report-directory:", "report-json:", "report-markdown:", "report-html:", "recovery-directory:", "artifact-manifest:", "integrity-credential:"))
    assert "MZ_INPUT_PATH: ${{ github.workspace }}/${{ inputs.path }}" in action
    assert "MZ_INPUT_METADATA: ${{ inputs.github-metadata }}" in action
    assert "MZ_INPUT_FALLBACK_PLAN: ${{ inputs.fallback-plan }}" in action
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
    assert "id: drill_unix" in action and "id: drill_windows" in action
    assert "steps.drill-unix" not in action and "steps.drill-windows" not in action
    for output_name in ("report-directory", "report-json", "report-markdown", "report-html", "recovery-directory", "artifact-manifest", "integrity-credential"):
        assert f"outputs['{output_name}']" in action
    assert "  history:" in action
    assert "MZ_INPUT_HISTORY: ${{ inputs.history }}" in action

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
    assert lines[2].endswith("report.md")
    assert lines[3].endswith("report.html")
    assert lines[4].endswith("recovery")


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


def test_action_adapter_normalizes_dotdot_before_runner_temp_boundary(tmp_path):
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    outside = tmp_path / "outside-output"
    with pytest.raises(ValueError, match="inside RUNNER_TEMP"):
        _write_outputs({
            "MZ_INPUT_OUTPUT": str(tmp_path / "reports"),
            "GITHUB_OUTPUT": str(runner_temp / "nested" / ".." / ".." / outside.name),
            "RUNNER_TEMP": str(runner_temp),
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


def test_action_adapter_rejects_symlinked_github_output_parent(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="symbolic link or reparse point"):
        _write_outputs({"MZ_INPUT_OUTPUT": str(tmp_path / "reports"), "GITHUB_OUTPUT": str(linked / "github-output")})


def test_action_adapter_rejects_reparse_output_parent_without_following_it(tmp_path, monkeypatch):
    linked = tmp_path / "linked-parent"
    linked.mkdir()
    output_file = linked / "github-output"
    original_lstat = Path.lstat

    def fake_lstat(path, *args, **kwargs):
        if path == linked:
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(ValueError, match="symbolic link or reparse point"):
        _write_outputs({"MZ_INPUT_OUTPUT": str(tmp_path / "reports"), "GITHUB_OUTPUT": str(output_file)})
    assert not output_file.exists()


def test_action_adapter_rejects_reparse_output_file_without_writing(tmp_path, monkeypatch):
    output_file = tmp_path / "github-output"
    output_file.write_text("keep\n", encoding="utf-8")
    original_lstat = Path.lstat

    def fake_lstat(path, *args, **kwargs):
        if path == output_file:
            return SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0x400)
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(ValueError, match="symbolic link"):
        _write_outputs({"MZ_INPUT_OUTPUT": str(tmp_path / "reports"), "GITHUB_OUTPUT": str(output_file)})
    assert output_file.read_text(encoding="utf-8") == "keep\n"


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


def test_action_adapter_rejects_special_github_output_before_open(tmp_path, monkeypatch):
    output_file = tmp_path / "github-output"
    output_file.write_text("keep\n", encoding="utf-8")
    original_lstat = Path.lstat

    def fake_lstat(path, *args, **kwargs):
        if path == output_file:
            return SimpleNamespace(st_mode=stat.S_IFIFO, st_file_attributes=0)
        return original_lstat(path, *args, **kwargs)

    def unexpected_open(*args, **kwargs):
        pytest.fail("special output must be rejected before a potentially blocking open")

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    monkeypatch.setattr(os, "open", unexpected_open)
    with pytest.raises(ValueError, match="regular file"):
        _write_outputs({"MZ_INPUT_OUTPUT": str(tmp_path / "reports"), "GITHUB_OUTPUT": str(output_file)})
    assert output_file.read_text(encoding="utf-8") == "keep\n"


def test_action_adapter_rejects_output_replacement_during_open(tmp_path, monkeypatch):
    output_file = tmp_path / "github-output"
    output_file.write_text("original\n", encoding="utf-8")
    moved = tmp_path / "old-output"
    original_open = os.open

    def replace_during_open(path, flags, *args, **kwargs):
        if Path(path) == output_file:
            output_file.rename(moved)
            output_file.write_text("replacement\n", encoding="utf-8")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", replace_during_open)
    with pytest.raises(ValueError, match="changed"):
        _write_outputs({"MZ_INPUT_OUTPUT": str(tmp_path / "reports"), "GITHUB_OUTPUT": str(output_file)})
    assert moved.read_text(encoding="utf-8") == "original\n"
    assert output_file.read_text(encoding="utf-8") == "replacement\n"


def test_action_adapter_rechecks_output_parent_identity_during_open(tmp_path, monkeypatch):
    parent = tmp_path / "runner-temp"
    parent.mkdir()
    output_file = parent / "github-output"
    output_file.write_text("keep\n", encoding="utf-8")
    moved = tmp_path / "moved-runner-temp"
    original_open = os.open

    def replace_parent_during_open(path, flags, *args, **kwargs):
        if Path(path) == output_file:
            parent.rename(moved)
            parent.mkdir()
            # Preserve the final file identity: checking only the output inode
            # is insufficient to prove that its parent chain is unchanged.
            (moved / output_file.name).rename(output_file)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", replace_parent_during_open)
    with pytest.raises(ValueError, match="parent.*changed"):
        _write_outputs({
            "MZ_INPUT_OUTPUT": str(tmp_path / "reports"),
            "GITHUB_OUTPUT": str(output_file),
            "RUNNER_TEMP": str(parent),
        })
    assert output_file.read_text(encoding="utf-8") == "keep\n"


def test_action_adapter_exclusive_creates_absent_output(tmp_path, monkeypatch):
    output_file = tmp_path / "github-output"
    original_open = os.open
    raced = False

    def create_during_open(path, flags, *args, **kwargs):
        nonlocal raced
        if Path(path) == output_file and not raced:
            raced = True
            output_file.write_text("attacker\n", encoding="utf-8")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", create_during_open)
    with pytest.raises(OSError, match="could not open GITHUB_OUTPUT"):
        _write_outputs({
            "MZ_INPUT_OUTPUT": str(tmp_path / "reports"),
            "GITHUB_OUTPUT": str(output_file),
        })
    assert raced
    assert output_file.read_text(encoding="utf-8") == "attacker\n"


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


def test_action_adapter_rejects_linked_workspace_components(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    linked = workspace / "linked"
    try:
        linked.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="symbolic link or reparse point"):
        build_argv({
            "MZ_INPUT_WORKSPACE": str(workspace),
            "MZ_INPUT_PATH": str(linked),
            "MZ_INPUT_OUTPUT": str(workspace / "reports"),
        })


def test_action_adapter_rejects_symlink_before_dotdot_component(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = workspace / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="symbolic link or reparse point"):
        build_argv({
            "MZ_INPUT_WORKSPACE": str(workspace),
            "MZ_INPUT_PATH": str(linked / ".." / "repository"),
        })


def test_action_adapter_rejects_lexical_dotdot_escape_after_missing_component(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(ValueError, match="inside the GitHub workspace"):
        build_argv({
            "MZ_INPUT_WORKSPACE": str(workspace),
            "MZ_INPUT_PATH": str(workspace / "missing" / ".." / ".." / "outside"),
        })


def test_action_adapter_rejects_symlinked_workspace_and_runner_temp(tmp_path):
    real_workspace = tmp_path / "workspace"
    real_workspace.mkdir()
    linked_workspace = tmp_path / "workspace-link"
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    linked_temp = tmp_path / "runner-temp-link"
    try:
        linked_workspace.symlink_to(real_workspace, target_is_directory=True)
        linked_temp.symlink_to(runner_temp, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="symbolic link or reparse point"):
        build_argv({
            "MZ_INPUT_WORKSPACE": str(linked_workspace),
            "MZ_INPUT_PATH": str(real_workspace),
        })
    with pytest.raises(ValueError, match="symbolic link or reparse point"):
        _write_outputs({
            "MZ_INPUT_OUTPUT": str(real_workspace / "reports"),
            "GITHUB_OUTPUT": str(runner_temp / "github-output"),
            "RUNNER_TEMP": str(linked_temp),
        })


def test_action_adapter_passes_fallback_plan_as_one_workspace_argv(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    plan = workspace / "fallback.json"
    argv = build_argv({
        "MZ_INPUT_WORKSPACE": str(workspace),
        "MZ_INPUT_PATH": str(workspace),
        "MZ_INPUT_OUTPUT": str(workspace / "reports"),
        "MZ_INPUT_FALLBACK_PLAN": str(plan),
    })
    assert argv[-2:] == ["--fallback-plan", str(plan)]


def test_action_adapter_passes_history_as_one_workspace_argv(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    history = workspace / "history.json"
    argv = build_argv({
        "MZ_INPUT_WORKSPACE": str(workspace),
        "MZ_INPUT_PATH": str(workspace),
        "MZ_INPUT_OUTPUT": str(workspace / "reports"),
        "MZ_INPUT_HISTORY": str(history),
    })
    assert argv[-2:] == ["--history", str(history)]


def test_action_adapter_bounds_history_to_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(ValueError, match="inside the GitHub workspace"):
        build_argv({
            "MZ_INPUT_WORKSPACE": str(workspace),
            "MZ_INPUT_PATH": str(workspace),
            "MZ_INPUT_OUTPUT": str(workspace / "reports"),
            "MZ_INPUT_HISTORY": str(workspace.parent / "outside.json"),
        })
