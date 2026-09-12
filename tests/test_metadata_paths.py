"""Cross-platform path boundary checks, even without symlink privileges."""

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from maintainer_zero.github_cache import (
    MetadataCacheError, cache_status, load_metadata_cache, save_metadata_cache,
)
from maintainer_zero.github_metadata import MetadataError, load_metadata


def snapshot():
    return {
        "schema_version": 1, "permissions": {"issues": True},
        "data": {"issues": [{"number": 1}]},
    }


@pytest.mark.parametrize("kind", ["symlink", "reparse"])
def test_parent_redirection_rejected_before_read_or_write(tmp_path, monkeypatch, kind):
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    target = blocked / "cache.json"
    save_metadata_cache(target, snapshot())
    original = target.read_bytes()
    path = target
    lstat = Path.lstat

    def fake_lstat(self, *args, **kwargs):
        if self == blocked:
            return SimpleNamespace(
                st_mode=stat.S_IFLNK if kind == "symlink" else stat.S_IFDIR,
                st_file_attributes=1024 if kind == "reparse" else 0,
            )
        return lstat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(MetadataError, match="symlink|reparse"):
        load_metadata(path)
    with pytest.raises(MetadataCacheError, match="symlink|reparse"):
        load_metadata_cache(path)
    with pytest.raises(MetadataCacheError, match="symlink|reparse"):
        save_metadata_cache(path, snapshot())
    assert cache_status(path).state == "invalid"
    assert target.read_bytes() == original
    assert not list(tmp_path.rglob("*.tmp"))


def test_cache_writer_rejects_dangling_target_without_replacement(tmp_path, monkeypatch):
    target = tmp_path / "cache.json"
    lstat = Path.lstat

    def dangling_lstat(self, *args, **kwargs):
        if self == target:
            return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
        return lstat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", dangling_lstat)
    with pytest.raises(MetadataCacheError, match="regular file"):
        save_metadata_cache(target, snapshot())
    assert not target.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_normal_relative_paths_and_new_cache_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    expected = save_metadata_cache("new/nested/cache.json", snapshot())
    assert load_metadata_cache("new/nested/cache.json") == expected
    assert load_metadata("new/nested/../nested/cache.json") == expected
    assert cache_status("missing/parent/cache.json").state == "missing"


def test_non_directory_parent_is_rejected_without_changing_file(tmp_path):
    parent = tmp_path / "file"
    parent.write_text("keep", encoding="utf-8")
    target = parent / "cache.json"
    with pytest.raises(MetadataError, match="directory"):
        load_metadata(target)
    with pytest.raises(MetadataCacheError, match="directory"):
        save_metadata_cache(target, snapshot())
    assert cache_status(target).state == "invalid"
    assert parent.read_text(encoding="utf-8") == "keep"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction integration")
def test_real_windows_junction_is_rejected(tmp_path):
    import _winapi

    real = tmp_path / "real"
    real.mkdir()
    target = real / "cache.json"
    save_metadata_cache(target, snapshot())
    original = target.read_bytes()
    junction = tmp_path / "junction"
    try:
        _winapi.CreateJunction(str(real), str(junction))
    except OSError as exc:
        pytest.skip(f"junction creation unavailable: {exc.winerror}")
    try:
        with pytest.raises(MetadataError, match="reparse point"):
            load_metadata(junction / target.name)
        with pytest.raises(MetadataCacheError, match="reparse point"):
            load_metadata_cache(junction / target.name)
        with pytest.raises(MetadataCacheError, match="reparse point"):
            save_metadata_cache(junction / "nested" / target.name, snapshot())
        assert cache_status(junction / target.name).state == "invalid"
        assert target.read_bytes() == original
        assert not (real / "nested").exists()
    finally:
        # Remove only the junction entry, never its destination.
        junction.rmdir()
