from pathlib import Path

import pytest

from maintainer_zero.fallback import FallbackPlanError, load_fallback_plan, summarize_fallback_plan


def _write(path: Path, payload: str):
    path.write_text(payload, encoding="utf-8")


def test_load_and_summarize_data_only_plan(tmp_path: Path):
    path = tmp_path / "fallback.json"
    _write(path, "{\"schema_version\":1,\"dependencies\":[{\"name\":\"requests\",\"replacement\":\"internal-mirror\",\"source\":\"mirror\",\"cold_build\":{\"status\":\"planned\",\"recorded_at\":\"2026-09-12\"}}]}")
    plan = load_fallback_plan(path)
    summary = summarize_fallback_plan(plan)
    assert summary["dependency_count"] == 1
    assert summary["cold_build_status_counts"]["planned"] == 1
    assert summary["execution"] == "not-run"


@pytest.mark.parametrize("payload", [
    "{\"schema_version\":1,\"dependencies\":[{\"name\":\"a\",\"replacement\":\"b\",\"source\":\"mirror\",\"cold_build\":{\"status\":\"planned\",\"recorded_at\":\"x\"},\"extra\":1}]}",
    "{\"schema_version\":1,\"dependencies\":[{\"name\":\"a\",\"replacement\":\"b\",\"source\":\"exec\",\"cold_build\":{\"status\":\"planned\",\"recorded_at\":\"x\"}}]}",
])
def test_plan_rejects_unknown_fields_and_sources(tmp_path: Path, payload: str):
    path = tmp_path / "fallback.json"
    _write(path, payload)
    with pytest.raises(FallbackPlanError):
        load_fallback_plan(path)


def test_plan_rejects_symlink(tmp_path: Path):
    target = tmp_path / "real.json"
    _write(target, "{\"schema_version\":1,\"dependencies\":[]}")
    link = tmp_path / "fallback.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(FallbackPlanError):
        load_fallback_plan(link)
