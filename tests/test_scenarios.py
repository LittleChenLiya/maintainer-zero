from pathlib import Path

import pytest
import json
import shutil
import subprocess

from maintainer_zero.analyzer import snapshot_repository
from maintainer_zero.cli import _anonymize_snapshot, _build_parser, _load_config, main
from maintainer_zero.models import RepoSnapshot
from maintainer_zero.scenarios import ci_outage, dependency_yanked, maintainer_zero

def repo(**kwargs):
    defaults = dict(path=".", name="demo", commits=100, contributors={"A": 80, "B": 20}, dependencies=["requests", "numpy"], workflows=["ci.yml"], codeowners={"*": ["@a"]}, release_files=[".github/workflows/release.yml"])
    defaults.update(kwargs)
    return RepoSnapshot(**defaults)

def test_maintainer_drill_flags_single_point():
    result = maintainer_zero(repo())
    assert result.scenario == "maintainer-zero"
    assert 0 <= result.score <= 100
    assert any(f.title == "核心维护单点" for f in result.findings)
    assert result.metrics["departed_maintainer"] == "A"
    assert result.findings[0].finding_id == "maintainer-zero.core-owner"
    assert {item.field for item in result.evidence} >= {"commits", "top_contributor_share", "ending_backlog"}

def test_dependency_drill_is_deterministic():
    first = dependency_yanked(repo())
    second = dependency_yanked(repo())
    assert first.to_dict() == second.to_dict()
    assert first.metrics["dependency_count"] == 2
    assert first.to_dict()["evidence"] == second.to_dict()["evidence"]

def test_ci_drill_detects_release_path():
    result = ci_outage(repo())
    assert result.metrics["release_path_detected"] is True
    assert result.findings[0].severity == "high"


def test_snapshot_rejects_non_git_directory(tmp_path):
    with pytest.raises(ValueError, match="Not a Git repository"):
        snapshot_repository(tmp_path)


def test_snapshot_rejects_linked_repository_before_git_probe(tmp_path, monkeypatch):
    real_repo = tmp_path / "real-repo"
    real_repo.mkdir()
    linked_repo = tmp_path / "linked-repo"
    try:
        linked_repo.symlink_to(real_repo, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")

    def unexpected_git(*args, **kwargs):
        raise AssertionError("linked repository must fail before git access")

    monkeypatch.setattr("maintainer_zero.analyzer.subprocess.run", unexpected_git)
    with pytest.raises(ValueError, match="repository may not be a symlink"):
        snapshot_repository(linked_repo)


def test_snapshot_rejects_linked_repository_parent(tmp_path):
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    repo_path = real_parent / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repo_path, check=True, capture_output=True)
    linked_parent = tmp_path / "linked-parent"
    try:
        linked_parent.symlink_to(real_parent, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="repository may not be a symlink"):
        snapshot_repository(linked_parent / "repo")


def test_snapshot_rejects_reparse_repository_without_git_probe(tmp_path, monkeypatch):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    original_lstat = Path.lstat

    def fake_lstat(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if path == repo_path:
            class ReparseInfo:
                st_mode = info.st_mode
                st_file_attributes = 0x400
            return ReparseInfo()
        return info

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(ValueError, match="repository may not be a symlink or reparse point"):
        snapshot_repository(repo_path)


@pytest.mark.parametrize("contents", [
    "{not-json}",
    "[]",
    '{"dependencies": []}',
])
def test_snapshot_rejects_malformed_package_manifest(tmp_path, contents):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repo_path, check=True, capture_output=True)
    (repo_path / "package.json").write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid dependency manifest"):
        snapshot_repository(repo_path)


def test_snapshot_does_not_follow_repository_symlink_outside_root(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repo_path, check=True, capture_output=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "requirements.txt").write_text("outside-package==1\n", encoding="utf-8")
    try:
        (repo_path / "requirements.txt").symlink_to(outside / "requirements.txt")
        (repo_path / ".github").mkdir()
        (repo_path / ".github" / "workflows").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    snapshot = snapshot_repository(repo_path)
    assert "outside-package" not in snapshot.dependencies
    assert snapshot.workflows == []


def test_snapshot_bounds_repository_declaration_files(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repo_path, check=True, capture_output=True)
    (repo_path / "package.json").write_bytes(b"{" + b" " * 1_048_576 + b"}")
    with pytest.raises(ValueError, match="exceeds size limit"):
        snapshot_repository(repo_path)


def test_snapshot_rejects_reparse_declaration_file_without_reading(tmp_path, monkeypatch):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repo_path, check=True, capture_output=True)
    package = repo_path / "package.json"
    package.write_text('{"dependencies": {"safe": "1"}}', encoding="utf-8")
    original_lstat = Path.lstat

    def fake_lstat(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if path == package:
            class ReparseInfo:
                st_mode = info.st_mode
                st_file_attributes = 0x400
            return ReparseInfo()
        return info

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    snapshot = snapshot_repository(repo_path)
    assert snapshot.dependencies == []


def test_snapshot_fails_closed_when_declaration_changes_during_read(tmp_path, monkeypatch):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repo_path, check=True, capture_output=True)
    package = repo_path / "package.json"
    package.write_text('{"dependencies": {"safe": "1"}}', encoding="utf-8")
    original_lstat = Path.lstat
    calls = 0

    def fake_lstat(path, *args, **kwargs):
        nonlocal calls
        info = original_lstat(path, *args, **kwargs)
        if path == package:
            calls += 1
            if calls == 2:
                package.write_text('{"dependencies": {"changed": "1"}}', encoding="utf-8")
                info = original_lstat(path, *args, **kwargs)
        return info

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(ValueError, match="changed during reading"):
        snapshot_repository(repo_path)


def test_config_is_validated_and_people_can_be_anonymized(tmp_path):
    (tmp_path / "continuity.json").write_text(
        '{"scenarios": ["ci-outage"], "days": 7, '
        '"privacy": {"anonymize_people": true, "upload_repository_content": false}}',
        encoding="utf-8",
    )
    config = _load_config(tmp_path)
    assert config["scenarios"] == ["ci-outage"]
    assert config["days"] == 7
    anonymized = _anonymize_snapshot(repo(contributors={"Zed": 2, "Amy": 1}))
    assert anonymized.contributors == {"contributor-2": 2, "contributor-1": 1}


def test_init_creates_valid_config_and_is_idempotent(tmp_path):
    assert main(["init", str(tmp_path)]) == 0
    config_path = tmp_path / "continuity.json"
    first = config_path.read_text(encoding="utf-8")
    assert _load_config(tmp_path)["days"] == 90

    config_path.write_text("{\"days\": 14}", encoding="utf-8")
    assert main(["init", str(tmp_path)]) == 0
    assert config_path.read_text(encoding="utf-8") == "{\"days\": 14}"
    assert first.endswith("\n")


def test_init_write_failure_leaves_no_partial_config_or_temp_file(tmp_path, monkeypatch, capsys):
    import maintainer_zero.cli as cli_module

    def fail_replace(source, target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(cli_module.os, "replace", fail_replace)
    assert main(["init", str(tmp_path)]) == 2
    assert not (tmp_path / "continuity.json").exists()
    assert not list(tmp_path.glob(".continuity.json.*.tmp"))
    assert "cannot write starter config" in capsys.readouterr().out


def test_init_rejects_symlinked_target_before_writing(tmp_path, capsys):
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    assert main(["init", str(linked)]) == 2
    assert not (outside / "continuity.json").exists()
    assert "cannot write starter config" in capsys.readouterr().out


def test_init_rejects_symlinked_config_without_following_existing_file(tmp_path, capsys):
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_config = outside / "continuity.json"
    outside_config.write_text('{"days": 14}', encoding="utf-8")
    linked_config = tmp_path / "continuity.json"
    try:
        linked_config.symlink_to(outside_config)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    assert main(["init", str(tmp_path)]) == 2
    assert outside_config.read_text(encoding="utf-8") == '{"days": 14}'
    assert "cannot write starter config" in capsys.readouterr().out


def test_init_rejects_reparse_target_without_following_it(tmp_path, monkeypatch, capsys):
    target = tmp_path / "reparse-target"
    target.mkdir()
    original_lstat = Path.lstat

    def fake_lstat(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if path == target:
            class ReparseInfo:
                st_mode = info.st_mode
                st_file_attributes = 0x400
            return ReparseInfo()
        return info

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    assert main(["init", str(target)]) == 2
    assert not (target / "continuity.json").exists()
    assert "cannot write starter config" in capsys.readouterr().out


def test_repository_anonymization_redacts_path_and_is_stable():
    original = repo(path="C:/private/acme-secret", name="acme-secret")
    first = _anonymize_snapshot(original, anonymize_people=False, anonymize_repository=True)
    second = _anonymize_snapshot(original, anonymize_people=False, anonymize_repository=True)
    assert first == second
    assert first.path == "<local-repository>"
    assert first.name.startswith("repository-")
    assert "acme-secret" not in first.name
    assert "C:/private" not in first.path


def test_config_accepts_repository_anonymization(tmp_path):
    (tmp_path / "continuity.json").write_text(
        '{"privacy": {"anonymize_repository": true}}', encoding="utf-8"
    )
    assert _load_config(tmp_path)["privacy"]["anonymize_repository"] is True


def test_cli_report_records_disabled_anonymization_configuration(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Fixture Maintainer"], cwd=repo_path, check=True)
    (repo_path / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "fixture"], cwd=repo_path, check=True, capture_output=True)
    (repo_path / "continuity.json").write_text(
        '{"privacy": {"anonymize_people": false, "anonymize_repository": false, '
        '"upload_repository_content": false}}',
        encoding="utf-8",
    )

    output = tmp_path / "output"
    assert main(["simulate", str(repo_path), "--scenario", "ci-outage", "--output", str(output)]) == 0
    report = json.loads((output / "continuity.json").read_text(encoding="utf-8"))
    assert report["privacy"] == {
        "anonymize_people": False,
        "anonymize_repository": False,
        "upload_repository_content": False,
    }
    markdown = (output / "report.md").read_text(encoding="utf-8")
    assert "Contributor and CODEOWNERS identities: **present**" in markdown
    assert "Repository name and path: **present**" in markdown


def test_config_rejects_unsupported_uploads(tmp_path):
    (tmp_path / "continuity.json").write_text(
        '{"privacy": {"upload_repository_content": true}}', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="uploads are not supported"):
        _load_config(tmp_path)


@pytest.mark.parametrize("value, message", [
    ('{"future_option": true}', "unsupported fields"),
    ('{"privacy": {"future_option": true}}', "privacy contains unsupported fields"),
])
def test_config_rejects_unknown_options_instead_of_silently_ignoring(tmp_path, value, message):
    (tmp_path / "continuity.json").write_text(value, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        _load_config(tmp_path)


@pytest.mark.parametrize("value", ['{"scenarios": null}', '{"scenarios": [{}]}', '{"days": null}'])
def test_config_rejects_null_and_non_string_values(tmp_path, value):
    (tmp_path / "continuity.json").write_text(value, encoding="utf-8")
    with pytest.raises(ValueError):
        _load_config(tmp_path)


def test_config_rejects_duplicate_keys_and_nonstandard_numbers(tmp_path):
    config_path = tmp_path / "continuity.json"
    config_path.write_text('{"days": 7, "days": 8}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate object key"):
        _load_config(tmp_path)
    config_path.write_text('{"days": NaN}', encoding="utf-8")
    with pytest.raises(ValueError, match="non-standard JSON number"):
        _load_config(tmp_path)


def test_config_rejects_oversized_file(tmp_path):
    config_path = tmp_path / "continuity.json"
    config_path.write_bytes(b"{" + b" " * (1_048_576) + b"}")
    with pytest.raises(ValueError, match="exceeds 1048576 bytes"):
        _load_config(tmp_path)


def test_config_rejects_symlinked_target_and_parent(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "continuity.json").write_text('{"days": 1}', encoding="utf-8")
    linked_file = tmp_path / "continuity.json"
    linked_parent = tmp_path / "linked-parent"
    try:
        linked_file.symlink_to(outside / "continuity.json")
        with pytest.raises(ValueError, match="regular file"):
            _load_config(tmp_path)
        linked_file.unlink()
        linked_parent.symlink_to(outside, target_is_directory=True)
        with pytest.raises(ValueError, match="symlink or reparse"):
            _load_config(linked_parent)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")


def test_config_rejects_reparse_target_without_reading(tmp_path, monkeypatch):
    config_path = tmp_path / "continuity.json"
    config_path.write_text('{"days": 1}', encoding="utf-8")
    original_lstat = Path.lstat

    def fake_lstat(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if path == config_path:
            class ReparseInfo:
                st_mode = info.st_mode
                st_file_attributes = 0x400
            return ReparseInfo()
        return info

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(ValueError, match="regular file"):
        _load_config(tmp_path)


def test_config_fails_closed_when_replaced_during_read(tmp_path, monkeypatch):
    config_path = tmp_path / "continuity.json"
    config_path.write_text('{"days": 1}', encoding="utf-8")
    original_lstat = Path.lstat
    calls = 0

    def fake_lstat(path, *args, **kwargs):
        nonlocal calls
        info = original_lstat(path, *args, **kwargs)
        if path == config_path:
            calls += 1
            if calls == 2:
                config_path.write_text('{"days": 100}', encoding="utf-8")
                info = original_lstat(path, *args, **kwargs)
        return info

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(ValueError, match="changed during reading"):
        _load_config(tmp_path)


@pytest.mark.parametrize("scenario", [maintainer_zero, dependency_yanked, ci_outage])
def test_scenarios_reject_negative_days(scenario):
    with pytest.raises(ValueError, match="days must be a non-negative integer"):
        scenario(repo(), -1)


def test_timeline_respects_short_drill_window():
    result = ci_outage(repo(), 1)
    assert [item["day"] for item in result.timeline] == [0, 1]


def test_dependency_drill_marks_empty_manifest_not_applicable():
    result = dependency_yanked(repo(dependencies=[]))
    assert result.metrics["applicable"] is False
    assert result.findings[0].severity == "info"
    assert result.timeline == [{"day": 0, "event": "场景跳过", "impact": "当前采集范围没有可模拟的依赖"}]


def test_maintainer_drill_exposes_deterministic_queue_metrics():
    result = maintainer_zero(repo(), 3)
    assert result.metrics["simulated_peak_backlog"] > 0
    assert result.metrics["simulated_ending_backlog"] > 0
    assert 0 <= result.metrics["simulated_service_level"] <= 1
    assert [item["day"] for item in result.timeline] == [0, 3]


@pytest.mark.parametrize("scenario, days", [(dependency_yanked, 3), (ci_outage, 3)])
def test_all_applicable_drills_expose_recovery_queue_metrics(scenario, days):
    result = scenario(repo(), days)
    metrics = result.metrics
    assert metrics["simulated_peak_backlog"] >= 0
    assert metrics["simulated_ending_backlog"] >= 0
    assert 0 <= metrics["simulated_service_level"] <= 1
    assert metrics["simulated_recovery_window_days"] == 7
    assert metrics["simulated_recovery_ending_backlog"] >= 0
    assert metrics["simulated_recovery_day"] is not None
    assert any(item.field == "recovery_day" for item in result.evidence)


def test_non_applicable_dependency_drill_marks_queue_metrics_unknown():
    result = dependency_yanked(repo(dependencies=[]), 3)
    assert result.metrics["simulated_recovery_window_days"] == 7
    assert result.metrics["simulated_recovery_day"] is None
    assert result.metrics["simulated_recovery_ending_backlog"] is None


def test_fail_under_is_parsed_and_invalid_config_rejected(tmp_path):
    parser = _build_parser()
    args = parser.parse_args(["simulate", ".", "--fail-under", "70"])
    assert args.fail_under == 70
    (tmp_path / "continuity.json").write_text('{"fail_under": 101}', encoding="utf-8")
    with pytest.raises(ValueError, match="fail_under"):
        _load_config(tmp_path)


def test_baseline_gate_policies_are_explicit():
    parser = _build_parser()
    args = parser.parse_args(["simulate", ".", "--baseline", "old.json", "--fail-on-new-high-risk"])
    assert args.fail_on_score_decrease is False
    assert args.fail_on_new_high_risk is True


def test_validate_scenario_command_is_read_only():
    parser = _build_parser()
    args = parser.parse_args(["validate-scenario", "examples/scenarios/dependency-yanked.json"])
    assert args.command == "validate-scenario"


def test_validate_registry_command_is_read_only_and_reports_errors(tmp_path, capsys):
    parser = _build_parser()
    args = parser.parse_args(["validate-registry", "maintainer_zero/scenario_registry.json"])
    assert args.command == "validate-registry"
    assert main(["validate-registry", "maintainer_zero/scenario_registry.json"]) == 0
    assert "Valid registry" in capsys.readouterr().out

    invalid = tmp_path / "registry.json"
    invalid.write_text("{}", encoding="utf-8")
    assert main(["validate-registry", str(invalid)]) == 2
    assert "error:" in capsys.readouterr().out


def test_describe_scenario_command_is_non_executable_and_supports_json(capsys):
    assert main(["describe-scenario", "maintainer_zero/scenario_registry.json", "--format", "json"]) == 2
    assert "error:" in capsys.readouterr().out
    assert main(["describe-scenario", "examples/scenarios/dependency-yanked.json", "--format", "json"]) == 0
    output = capsys.readouterr().out
    assert '"input_sources"' in output
    assert '"execution_mode": "declarative"' in output
    assert "entrypoint" not in output
