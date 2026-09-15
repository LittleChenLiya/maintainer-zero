"""Native CLI output boundaries retain path traversal until inspection."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from maintainer_zero.cli import _safe_output_directory, _safe_output_file


@pytest.mark.parametrize("kind", ["directory", "file"])
def test_output_checks_reparse_component_before_parent_traversal(tmp_path, monkeypatch, kind):
    linked = tmp_path / "linked"
    linked.mkdir()
    original_lstat = Path.lstat

    def reparse_lstat(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if path == linked:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", reparse_lstat)
    target = linked / ".." / "new-output"
    check = _safe_output_directory if kind == "directory" else _safe_output_file
    if kind == "file":
        target /= "result.json"
    with pytest.raises(ValueError, match="symlink"):
        check(target)
    assert not (tmp_path / "new-output").exists()


@pytest.mark.parametrize("kind", ["directory", "file"])
def test_output_allows_parent_traversal_through_real_directory(tmp_path, kind):
    real = tmp_path / "real"
    real.mkdir()
    target = real / ".." / "new-output"
    expected = tmp_path / "new-output"
    check = _safe_output_directory if kind == "directory" else _safe_output_file
    if kind == "file":
        target /= "result.json"
        expected /= "result.json"
    assert check(target) == expected
