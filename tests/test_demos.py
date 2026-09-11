from pathlib import Path

import pytest

from maintainer_zero.demos import DemoError, load_demo_suite, run_demo_suite
from maintainer_zero.cli import main
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
    assert main(["demo", str(DEMO_PATH), "--format", "json"]) == 0
    output = capsys.readouterr().out
    assert '"schema_version": 1' in output
    assert '"maintainer-handoff"' in output


def test_demo_cli_writes_output_and_alias_is_supported(tmp_path):
    output = tmp_path / "nested" / "demo.json"
    assert main(["demos", str(DEMO_PATH), "--format", "json", "--output", str(output)]) == 0
    assert output.exists()
    assert '"demos"' in output.read_text(encoding="utf-8")


def test_demo_cli_rejects_malformed_suite(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text('{"schema_version": 1, "demos": []}', encoding="utf-8")
    assert main(["demo", str(path)]) == 2
    assert "error:" in capsys.readouterr().out


def test_demo_cli_writes_deterministic_json(tmp_path):
    output = tmp_path / "demo-results.json"
    assert main(["demo", str(DEMO_PATH), "--output", str(output)]) == 0
    first = output.read_text(encoding="utf-8")
    assert "maintainer-handoff" in first
    assert main(["demo", str(DEMO_PATH), "--output", str(output)]) == 0
    assert output.read_text(encoding="utf-8") == first
