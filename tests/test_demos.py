from pathlib import Path
import json

import pytest
from types import SimpleNamespace

from maintainer_zero.demos import DemoError, _read_external_suite, load_demo_suite, run_demo_suite
from maintainer_zero.cli import main


DEMO_PATH = Path(__file__).parents[1] / "examples" / "demos" / "continuity-demos.json"


def test_demos_are_reproducible_and_improve_scores():
    suite = load_demo_suite(DEMO_PATH)
    first = run_demo_suite(suite)
    second = run_demo_suite(suite)
    assert first == second
    assert len(first) == 3
    assert all(item["improved"] for item in first)


def test_demos_reject_unknown_scenario():
    suite = load_demo_suite(DEMO_PATH)
    suite["demos"][0]["scenario"] = "arbitrary-code"
    with pytest.raises(DemoError, match="built-in scenario"):
        run_demo_suite(suite)


def test_demo_cli_renders_json_without_reading_a_repository(capsys):
    assert main(["demo", "--format", "json"]) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["schema_version"] == 1
    assert payload["results"][0]["id"] == "maintainer-handoff"


def test_demo_cli_writes_output_and_alias_is_supported(tmp_path):
    output = tmp_path / "nested" / "demo.json"
    assert main(["demos", str(DEMO_PATH), "--format", "json", "--output", str(output)]) == 0
    assert output.exists()
    assert '"results"' in output.read_text(encoding="utf-8")


def test_demo_cli_rejects_malformed_suite(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text('{"schema_version": 1, "demos": []}', encoding="utf-8")
    assert main(["demo", str(path)]) == 2
    assert "error:" in capsys.readouterr().out


def test_demo_cli_gate_returns_one_when_after_does_not_improve(tmp_path, capsys):
    payload = json.loads(DEMO_PATH.read_text(encoding="utf-8"))
    payload["demos"][0]["after"] = payload["demos"][0]["before"]
    path = tmp_path / "regression.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert main(["demo", str(path), "--fail-on-regression"]) == 1
    assert "Demo gate failed" in capsys.readouterr().out


def test_demo_cli_writes_deterministic_json(tmp_path):
    output = tmp_path / "demo-results.json"
    assert main(["demo", str(DEMO_PATH), "--output", str(output)]) == 0
    first = output.read_text(encoding="utf-8")
    assert "maintainer-handoff" in first
    assert main(["demo", str(DEMO_PATH), "--output", str(output)]) == 0
    assert output.read_text(encoding="utf-8") == first
    assert not list(tmp_path.glob(".demo-results.json.*.tmp"))


def test_demo_cli_write_failure_preserves_existing_output(tmp_path, monkeypatch, capsys):
    output = tmp_path / "demo-results.json"
    output.write_text("previous demo\n", encoding="utf-8")

    def fail_replace(source, target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("maintainer_zero.cli.os.replace", fail_replace)
    assert main(["demo", str(DEMO_PATH), "--format", "json", "--output", str(output)]) == 2
    assert output.read_text(encoding="utf-8") == "previous demo\n"
    assert not list(tmp_path.glob(".demo-results.json.*.tmp"))
    assert "cannot write demo output" in capsys.readouterr().out


def test_demo_cli_converts_unsafe_output_value_error_to_controlled_error(tmp_path, monkeypatch, capsys):
    output = tmp_path / "demo-results.json"

    def reject_output(path, content):
        raise ValueError("unsafe output path")

    monkeypatch.setattr("maintainer_zero.cli._atomic_write_text", reject_output)
    assert main(["demo", str(DEMO_PATH), "--format", "json", "--output", str(output)]) == 2
    assert "cannot write demo output" in capsys.readouterr().out


def test_demo_cli_rejects_symlinked_output_parent(tmp_path, monkeypatch, capsys):
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    assert main(["demo", str(DEMO_PATH), "--format", "json", "--output", str(linked / "demo.json")]) == 2
    assert "cannot write demo output" in capsys.readouterr().out


def test_demo_cli_does_not_create_nested_output_below_symlink_parent(tmp_path, capsys):
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")

    output = linked / "new" / "demo.json"
    assert main(["demo", str(DEMO_PATH), "--format", "json", "--output", str(output)]) == 2
    assert "cannot write demo output" in capsys.readouterr().out
    assert not (outside / "new").exists()


def test_demo_loader_rejects_ambiguous_json_and_replaced_file(tmp_path, monkeypatch):
    path = tmp_path / "demo.json"
    path.write_text('{"schema_version": 1, "schema_version": 1, "demos": []}', encoding="utf-8")
    with pytest.raises(DemoError, match="duplicate object key"):
        load_demo_suite(path)
    path.write_text('{"schema_version": 1, "demos": []}', encoding="utf-8")
    original_lstat = Path.lstat
    calls = 0

    def fake_lstat(value, *args, **kwargs):
        nonlocal calls
        info = original_lstat(value, *args, **kwargs)
        if value == path:
            calls += 1
            if calls == 2:
                path.write_text('{"schema_version": 1, "demos": []}', encoding="utf-8")
                info = original_lstat(value, *args, **kwargs)
        return info

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(DemoError, match="changed during reading"):
        load_demo_suite(path)
def test_demo_loader_rejects_link_hidden_before_dotdot_normalization(tmp_path, monkeypatch):
    linked = tmp_path / "linked"
    linked.mkdir()
    target = linked / ".." / "demo.json"
    original_lstat = Path.lstat

    def fake_lstat(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if path == linked:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(DemoError, match="real directory"):
        _read_external_suite(target)
