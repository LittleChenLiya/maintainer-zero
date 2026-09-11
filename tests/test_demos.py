from pathlib import Path

import pytest

from maintainer_zero.demos import DemoError, load_demo_suite, run_demo_suite
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


def test_demo_cli_writes_deterministic_json(tmp_path):
    output = tmp_path / "demo-results.json"
    assert main(["demo", str(DEMO_PATH), "--output", str(output)]) == 0
    first = output.read_text(encoding="utf-8")
    assert "maintainer-handoff" in first
    assert main(["demo", str(DEMO_PATH), "--output", str(output)]) == 0
    assert output.read_text(encoding="utf-8") == first
