import os
from pathlib import Path

import pytest

import tools.verify_release as release_verify
from tools.verify_release import DEFAULT_VERIFY_OUTPUT, verify


def test_release_verification_is_idempotent(tmp_path: Path):
    root = Path(__file__).parents[1]
    output = tmp_path / "release"

    verify(root, output)
    verify(root, output)

    assert len(list((output / "artifacts").glob("*.whl"))) == 1
    assert len(list((output / "artifacts").glob("*.tar.gz"))) == 1


def test_release_verification_default_output_is_an_absolute_codex_path():
    assert DEFAULT_VERIFY_OUTPUT.is_absolute()
    assert DEFAULT_VERIFY_OUTPUT == Path("D:/Codex/maintainer-zero-release-verify")


def test_release_verification_install_probe_is_offline_safe():
    source = (Path(__file__).parents[1] / "tools" / "verify_release.py").read_text(encoding="utf-8")
    assert "--no-build-isolation" in source, "release install must not resolve build dependencies from the network"
    assert source.count("--no-index") >= 2, "release build and install must not query package indexes"


def test_release_install_probe_validates_packaged_data_contracts():
    source = (Path(__file__).parents[1] / "tools" / "verify_release.py").read_text(encoding="utf-8")
    # Importing the package is insufficient: wheels/sdists must retain the
    # bundled, data-only registry and demo fixture used by end users.
    assert "load_bundled_registry" in source
    assert "scenario_ids(registry)" in source
    assert "load_demo_suite()" in source
    assert "verify-manifest" in source and "verify-credential" in source, "release smoke must verify generated integrity artifacts"


def test_release_verification_rejects_output_inside_source_checkout(tmp_path: Path):
    root = Path(__file__).parents[1]
    with pytest.raises(ValueError, match="outside the source checkout"):
        verify(root, root / "release-output")


def test_release_verification_cli_returns_controlled_error_for_unsafe_output(tmp_path: Path, capsys):
    root = Path(__file__).parents[1]
    assert release_verify.main(["--root", str(root), "--output", str(root / "release-output")]) == 2
    assert capsys.readouterr().out.strip() == "error: release verification failed: ValueError"


def test_release_verification_rejects_symlinked_output_component(tmp_path: Path):
    root = Path(__file__).parents[1]
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked-output"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="may not contain a symlink or reparse point"):
        verify(root, linked / "release")


def test_release_verification_rejects_reparse_output_component(tmp_path: Path, monkeypatch):
    linked = tmp_path / "junction-like"
    linked.mkdir()
    original = release_verify._is_link_or_reparse

    # Simulate the Windows reparse attribute without requiring junction
    # privileges on the test host. The helper must still fail closed.
    original_lstat = release_verify.Path.lstat

    def fake_lstat(path):
        info = original_lstat(path)
        if path == linked:
            class ReparseInfo:
                st_mode = info.st_mode
                st_file_attributes = release_verify._REPARSE_POINT
            return ReparseInfo()
        return info

    monkeypatch.setattr(release_verify.Path, "lstat", fake_lstat)
    with pytest.raises(ValueError, match="symlink or reparse point"):
        release_verify._safe_output_directory(linked / "release")


def test_release_verification_rejects_linked_archive_in_existing_wheelhouse(tmp_path: Path):
    root = Path(__file__).parents[1]
    output = tmp_path / "release"
    wheelhouse = output / "artifacts"
    wheelhouse.mkdir(parents=True)
    target = tmp_path / "outside.whl"
    target.write_bytes(b"not an archive")
    linked = wheelhouse / "stale.whl"
    try:
        linked.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="archive target is unsafe"):
        verify(root, output)


def test_release_verification_rejects_dangling_wheelhouse_link(tmp_path: Path):
    root = Path(__file__).parents[1]
    output = tmp_path / "release"
    output.mkdir()
    wheelhouse = output / "artifacts"
    try:
        wheelhouse.symlink_to(tmp_path / "missing-wheelhouse", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="release artifact directory may not be a symlink"):
        verify(root, output)


def test_release_archive_contract_rejects_special_files_and_zero_size(tmp_path: Path):
    wheelhouse = tmp_path / "artifacts"
    wheelhouse.mkdir()
    wheel = wheelhouse / "maintainer_zero.whl"
    sdist = wheelhouse / "maintainer-zero.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    assert len(release_verify._safe_release_archives(wheelhouse)) == 2
    wheel.write_bytes(b"")
    with pytest.raises(ValueError, match="invalid size"):
        release_verify._safe_release_archives(wheelhouse)


def test_release_archive_is_staged_before_install_probe(tmp_path: Path):
    wheelhouse = tmp_path / "artifacts"
    install_dir = tmp_path / "install"
    wheelhouse.mkdir()
    install_dir.mkdir()
    archive = wheelhouse / "maintainer_zero.whl"
    archive.write_bytes(b"stable archive")
    staged = release_verify._stage_release_archive(archive, install_dir)
    assert staged.name == archive.name
    assert staged.read_bytes() == b"stable archive"
    assert staged.parent == install_dir
    archive.write_bytes(b"replacement")
    assert staged.read_bytes() == b"stable archive"


def test_release_archive_staging_rejects_source_replacement(tmp_path: Path, monkeypatch):
    wheelhouse = tmp_path / "artifacts"
    install_dir = tmp_path / "install"
    wheelhouse.mkdir()
    install_dir.mkdir()
    archive = wheelhouse / "maintainer_zero.whl"
    archive.write_bytes(b"archive")
    original_lstat = release_verify.Path.lstat
    calls = {"count": 0}
    original_mtime_ns = archive.stat().st_mtime_ns

    def replace_after_open(path):
        if path == archive:
            calls["count"] += 1
            if calls["count"] == 2:
                archive.write_bytes(b"changed")
                # Preserve size and timestamp so metadata-only checks cannot
                # detect this same-inode content replacement.
                os.utime(archive, ns=(original_mtime_ns, original_mtime_ns))
        return original_lstat(path)

    monkeypatch.setattr(release_verify.Path, "lstat", replace_after_open)
    with pytest.raises(ValueError, match="changed during staging"):
        release_verify._stage_release_archive(archive, install_dir)
