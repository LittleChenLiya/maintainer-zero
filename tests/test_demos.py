from pathlib import Path

import pytest

from maintainer_zero.demos import DemoError, load_demo_suite, run_demo_suite


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
