from pathlib import Path
from types import SimpleNamespace
import os

import pytest

from maintainer_zero.cli import main
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


def test_plan_rejects_descriptor_redirect_before_parsing(tmp_path: Path, monkeypatch):
    path = tmp_path / "fallback.json"
    _write(path, "{\"schema_version\":1,\"dependencies\":[]}")
    original_fstat = os.fstat
    def mismatched(fd):
        info = original_fstat(fd)
        return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=getattr(info, "st_file_attributes", 0), st_dev=info.st_dev, st_ino=info.st_ino + 1, st_size=info.st_size)
    monkeypatch.setattr("maintainer_zero.fallback.os.fstat", mismatched)
    with pytest.raises(FallbackPlanError, match="changed before"):
        load_fallback_plan(path)


def test_validate_fallback_plan_command_is_read_only_and_supports_json(tmp_path: Path, capsys):
    path = tmp_path / "fallback.json"
    _write(path, "{\"schema_version\":1,\"dependencies\":[]}")
    assert main(["validate-fallback-plan", str(path), "--format", "json"]) == 0
    output = capsys.readouterr().out
    assert '\"execution\": \"not-run\"' in output
    invalid = tmp_path / "invalid.json"
    _write(invalid, "{}")
    assert main(["validate-fallback-plan", str(invalid)]) == 2
    assert "error:" in capsys.readouterr().out
